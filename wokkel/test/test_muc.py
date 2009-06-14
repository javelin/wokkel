# Copyright (c) 2003-2009 Ralph Meijer
# See LICENSE for details.

"""
Tests for L{wokkel.muc}
"""

from zope.interface import verify

from twisted.trial import unittest
from twisted.internet import defer
from twisted.words.xish import domish, xpath
from twisted.words.protocols.jabber.jid import JID

from wokkel import data_form, iwokkel, muc, disco
from wokkel.test.helpers import XmlStreamStub

from twisted.words.protocols.jabber.xmlstream import toResponse

NS_MUC_ADMIN = 'http://jabber.org/protocol/muc#admin'

def calledAsync(fn):
    """
    Function wrapper that fires a deferred upon calling the given function.
    """
    d = defer.Deferred()

    def func(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except:
            d.errback()
        else:
            d.callback(result)

    return d, func



class MucClientTest(unittest.TestCase):
    timeout = 2

    def setUp(self):
        self.stub = XmlStreamStub()
        self.protocol = muc.MUCClient()
        self.protocol.xmlstream = self.stub.xmlstream
        self.protocol.connectionInitialized()
        self.test_room = 'test'
        self.test_srv  = 'conference.example.org'
        self.test_nick = 'Nick'

        self.room_jid = JID(self.test_room+'@'+self.test_srv+'/'+self.test_nick)

        self.user_jid = JID('test@jabber.org/Testing')


    def _createRoom(self):
        """
        A helper method to create a test room.
        """
        # create a room
        self.current_room = muc.Room(self.test_room, self.test_srv, self.test_nick)
        self.protocol._addRoom(self.current_room)


    def test_interface(self):
        """
        Do instances of L{muc.MUCClient} provide L{iwokkel.IMUCClient}?
        """
        verify.verifyObject(iwokkel.IMUCClient, self.protocol)


    def test_userJoinedRoom(self):
        """
        The client receives presence from an entity joining the room.

        This tests the class L{muc.UserPresence} and the userJoinedRoom event method.

        The test sends the user presence and tests if the event method is called.

        """
        p = muc.UserPresence()
        p['to'] = self.user_jid.full()
        p['from'] = self.room_jid.full()

        # create a room
        self._createRoom()

        def userPresence(room, user):
            self.failUnless(room.roomIdentifier==self.test_room, 'Wrong room name')
            self.failUnless(room.inRoster(user), 'User not in roster')


        d, self.protocol.userJoinedRoom = calledAsync(userPresence)
        self.stub.send(p)
        return d


    def test_groupChat(self):
        """
        The client receives a groupchat message from an entity in the room.
        """
        m = muc.GroupChat('test@test.com',body='test')
        m['from'] = self.room_jid.full()

        self._createRoom()

        def groupChat(room, user, message):
            self.failUnless(message=='test', "Wrong group chat message")
            self.failUnless(room.roomIdentifier==self.test_room, 'Wrong room name')


        d, self.protocol.receivedGroupChat = calledAsync(groupChat)
        self.stub.send(m)
        return d


    def test_joinRoom(self):
        """
        Joining a room
        """

        def cb(room):
            self.assertEquals(self.test_room, room.roomIdentifier)

        d = self.protocol.join(self.test_srv, self.test_room, self.test_nick)
        d.addCallback(cb)

        prs = self.stub.output[-1]
        self.failUnless(prs.name=='presence', "Need to be presence")
        self.failUnless(getattr(prs, 'x', None), 'No muc x element')

        # send back user presence, they joined
        response = muc.UserPresence(frm=self.test_room+'@'+self.test_srv+'/'+self.test_nick)
        self.stub.send(response)
        return d


    def test_joinRoomForbidden(self):
        """
        Client joining a room and getting a forbidden error.
        """

        def cb(error):

            self.failUnless(error.value.mucCondition=='forbidden','Wrong muc condition')



        d = self.protocol.join(self.test_srv, self.test_room, self.test_nick)
        d.addBoth(cb)

        prs = self.stub.output[-1]
        self.failUnless(prs.name=='presence', "Need to be presence")
        self.failUnless(getattr(prs, 'x', None), 'No muc x element')
        # send back user presence, they joined

        response = muc.PresenceError(error=muc.MUCError('auth',
                                                        'forbidden'
                                                        ),
                                     frm=self.room_jid.full())
        self.stub.send(response)
        return d


    def test_joinRoomBadJid(self):
        """
        Client joining a room and getting a forbidden error.
        """

        def cb(error):

            self.failUnless(error.value.mucCondition=='jid-malformed','Wrong muc condition')



        d = self.protocol.join(self.test_srv, self.test_room, self.test_nick)
        d.addBoth(cb)

        prs = self.stub.output[-1]
        self.failUnless(prs.name=='presence', "Need to be presence")
        self.failUnless(getattr(prs, 'x', None), 'No muc x element')
        # send back user presence, they joined

        response = muc.PresenceError(error=muc.MUCError('modify',
                                                        'jid-malformed'
                                                        ),
                                     frm=self.room_jid.full())
        self.stub.send(response)
        return d


    def test_partRoom(self):
        """
        Client leaves a room
        """
        def cb(left):
            self.failUnless(left, 'did not leave room')


        self._createRoom()
        d = self.protocol.leave(self.room_jid)
        d.addCallback(cb)

        prs = self.stub.output[-1]

        self.failUnless(prs['type']=='unavailable', 'Unavailable is not being sent')

        response = prs
        response['from'] = response['to']
        response['to'] = 'test@jabber.org'

        self.stub.send(response)
        return d


    def test_userPartsRoom(self):
        """
        An entity leaves the room, a presence of type unavailable is received by the client.
        """

        p = muc.UnavailableUserPresence()
        p['to'] = self.user_jid.full()
        p['from'] = self.room_jid.full()

        # create a room
        self._createRoom()
        # add user to room
        user = muc.User(self.room_jid.resource)

        room = self.protocol._getRoom(self.room_jid)
        room.addUser(user)

        def userPresence(room, user):
            self.failUnless(room.roomIdentifier==self.test_room, 'Wrong room name')
            self.failUnless(room.inRoster(user)==False, 'User in roster')

        d, self.protocol.userLeftRoom = calledAsync(userPresence)
        self.stub.send(p)
        return d


    def test_ban(self):
        """
        Ban an entity in a room.
        """
        banned = JID('ban@jabber.org/TroubleMakger')
        def cb(banned):
            self.failUnless(banned, 'Did not ban user')


        d = self.protocol.ban(self.room_jid, banned, reason='Spam',
                              sender=self.user_jid)
        d.addCallback(cb)

        iq = self.stub.output[-1]

        self.failUnless(xpath.matches("/iq[@type='set' and @to='%s']/query/item[@affiliation='outcast']" % (self.room_jid.userhost(),), iq), 'Wrong ban stanza')

        response = toResponse(iq, 'result')

        self.stub.send(response)

        return d


    def test_kick(self):
        """
        Kick an entity from a room.
        """
        nick = 'TroubleMakger'

        def cb(kicked):
            self.failUnless(kicked, 'Did not kick user')

        d = self.protocol.kick(self.room_jid, nick, reason='Spam',
                               sender=self.user_jid)
        d.addCallback(cb)

        iq = self.stub.output[-1]

        self.failUnless(xpath.matches("/iq[@type='set' and @to='%s']/query/item[@affiliation='none']" % (self.room_jid.userhost(),), iq), 'Wrong kick stanza')

        response = toResponse(iq, 'result')

        self.stub.send(response)

        return d


    def test_password(self):
        """
        Sending a password via presence to a password protected room.
        """

        self.protocol.password(self.room_jid, 'secret')

        prs = self.stub.output[-1]

        self.failUnless(xpath.matches("/presence[@to='%s']/x/password[text()='secret']" % (self.room_jid.full(),), prs), 'Wrong presence stanza')


    def test_history(self):
        """
        Receiving history on room join.
        """
        m = muc.HistoryMessage(self.room_jid.userhost(), self.protocol._makeTimeStamp(), body='test')
        m['from'] = self.room_jid.full()

        self._createRoom()

        def roomHistory(room, user, body, stamp, frm=None):
            self.failUnless(body=='test', "wrong message body")
            self.failUnless(stamp, 'Does not have a history stamp')


        d, self.protocol.receivedHistory = calledAsync(roomHistory)
        self.stub.send(m)
        return d


    def test_oneToOneChat(self):
        """
        Converting a one to one chat to a multi-user chat.
        """
        archive = []
        thread = "e0ffe42b28561960c6b12b944a092794b9683a38"
        # create messages
        msg = domish.Element((None, 'message'))
        msg['to'] = 'testing@example.com'
        msg['type'] = 'chat'
        msg.addElement('body', None, 'test')
        msg.addElement('thread', None, thread)

        archive.append({'stanza': msg, 'timestamp': '2002-10-13T23:58:37Z'})

        msg = domish.Element((None, 'message'))
        msg['to'] = 'testing2@example.com'
        msg['type'] = 'chat'
        msg.addElement('body', None, 'yo')
        msg.addElement('thread', None, thread)

        archive.append({'stanza': msg, 'timestamp': '2002-10-13T23:58:43Z'})

        self.protocol.history(self.room_jid, archive)


        while len(self.stub.output)>0:
            m = self.stub.output.pop()
            # check for delay element
            self.failUnless(m.name=='message', 'Wrong stanza')
            self.failUnless(xpath.matches("/message/delay", m), 'Invalid history stanza')


    def test_invite(self):
        """
        Invite a user to a room
        """
        bareRoomJID = self.room_jid.userhostJID()
        invitee = JID('test@jabber.org')

        self.protocol.invite(bareRoomJID, 'This is a test', invitee)

        msg = self.stub.output[-1]

        query = u"/message[@to='%s']/x/invite/reason" % bareRoomJID
        self.failUnless(xpath.matches(query, msg), 'Wrong message type')


    def test_privateMessage(self):
        """
        Send private messages to muc entities.
        """
        other_nick = self.room_jid.userhost()+'/OtherNick'

        self.protocol.chat(other_nick, 'This is a test')

        msg = self.stub.output[-1]

        self.failUnless(xpath.matches("/message[@type='chat' and @to='%s']/body" % (other_nick,), msg), 'Wrong message type')


    def test_register(self):
        """
        Client registering with a room. http://xmpp.org/extensions/xep-0045.html#register

        """

        def cb(iq):
            # check for a result
            self.failUnless(iq['type']=='result', 'We did not get a result')

        d = self.protocol.register(self.room_jid)
        d.addCallback(cb)

        iq = self.stub.output[-1]
        self.failUnless(xpath.matches("/iq/query[@xmlns='%s']" % (muc.NS_REQUEST), iq), 'Invalid iq register request')

        response = toResponse(iq, 'result')

        self.stub.send(response)
        return d


    def test_voice(self):
        """
        Client requesting voice for a room.
        """
        self.protocol.voice(self.room_jid)

        m = self.stub.output[-1]

        self.failUnless(xpath.matches("/message/x[@type='submit']/field/value[text()='%s']" % (muc.NS_MUC_REQUEST,), m), 'Invalid voice message stanza')


    def test_roomConfigure(self):
        """
        Default configure and changing the room name.
        """

        def cb(iq):
            self.failUnless(iq['type']=='result', 'Not a result')


        fields = []

        fields.append(data_form.Field(label='Natural-Language Room Name',
                                      var='muc#roomconfig_roomname',
                                      value=self.test_room))

        d = self.protocol.configure(self.room_jid.userhost(), fields)
        d.addCallback(cb)

        iq = self.stub.output[-1]
        self.failUnless(xpath.matches("/iq/query[@xmlns='%s']/x"% (muc.NS_MUC_OWNER,), iq), 'Bad configure request')

        response = toResponse(iq, 'result')
        self.stub.send(response)
        return d


    def test_roomDestroy(self):
        """
        Destroy a room.
        """

        def cb(destroyed):
            self.failUnless(destroyed==True, 'Room not destroyed.')

        d = self.protocol.destroy(self.room_jid)
        d.addCallback(cb)

        iq = self.stub.output[-1]
        self.failUnless(xpath.matches("/iq/query[@xmlns='%s']/destroy"% (muc.NS_MUC_OWNER,), iq), 'Bad configure request')

        response = toResponse(iq, 'result')
        self.stub.send(response)
        return d


    def test_nickChange(self):
        """
        Send a nick change to the server.
        """
        test_nick = 'newNick'

        self._createRoom()

        def cb(room):
            self.assertEquals(self.test_room, room.roomIdentifier)
            self.assertEquals(test_nick, room.nick)

        d = self.protocol.nick(self.room_jid, test_nick)
        d.addCallback(cb)

        prs = self.stub.output[-1]
        self.failUnless(prs.name=='presence', "Need to be presence")
        self.failUnless(getattr(prs, 'x', None), 'No muc x element')

        # send back user presence, they joined
        response = muc.UserPresence(frm=self.test_room+'@'+self.test_srv+'/'+test_nick)

        self.stub.send(response)
        return d


    def test_grantVoice(self):
        """
        Test granting voice to a user.

        """
        nick = 'TroubleMakger'
        def cb(give_voice):
            self.failUnless(give_voice, 'Did not give voice user')


        d = self.protocol.grantVoice(self.room_jid, nick, sender=self.user_jid)
        d.addCallback(cb)

        iq = self.stub.output[-1]

        self.failUnless(xpath.matches("/iq[@type='set' and @to='%s']/query/item[@role='participant']" % (self.room_jid.userhost(),), iq), 'Wrong voice stanza')

        response = toResponse(iq, 'result')

        self.stub.send(response)

        return d


    def test_changeStatus(self):
        """
        Change status
        """
        self._createRoom()
        room = self.protocol._getRoom(self.room_jid)
        user = muc.User(self.room_jid.resource)
        room.addUser(user)

        def cb(room):
            self.assertEquals(self.test_room, room.roomIdentifier)
            user = room.getUser(self.room_jid.resource)
            self.failUnless(user is not None, 'User not found')
            self.failUnless(user.status == 'testing MUC', 'Wrong status')
            self.failUnless(user.show == 'xa', 'Wrong show')

        d = self.protocol.status(self.room_jid, 'xa', 'testing MUC')
        d.addCallback(cb)

        prs = self.stub.output[-1]

        self.failUnless(prs.name=='presence', "Need to be presence")
        self.failUnless(getattr(prs, 'x', None), 'No muc x element')

        # send back user presence, they joined
        response = muc.UserPresence(frm=self.room_jid.full())
        response.addElement('show', None, 'xa')
        response.addElement('status', None, 'testing MUC')
        self.stub.send(response)
        return d


    def test_getMemberList(self):
        def cb(room):
            members = room.members
            self.assertEqual(1, len(members))
            user = members[0]
            self.assertEquals(JID(u'hag66@shakespeare.lit'), user.entity)
            self.assertEquals(u'thirdwitch', user.nick)
            self.assertEquals(u'participant', user.role)

        self._createRoom()
        bareRoomJID = self.room_jid.userhostJID()
        d = self.protocol.getMemberList(bareRoomJID)
        d.addCallback(cb)

        iq = self.stub.output[-1]
        query = iq.query
        self.assertNotIdentical(None, query)
        self.assertEquals(NS_MUC_ADMIN, query.uri)

        response = toResponse(iq, 'result')
        query = response.addElement((NS_MUC_ADMIN, 'query'))
        item = query.addElement('item')
        item['affiliation'] ='member'
        item['jid'] = 'hag66@shakespeare.lit'
        item['nick'] = 'thirdwitch'
        item['role'] = 'participant'
        self.stub.send(response)

        return d


