import unittest

from nanomsg import Message
from nanomsg import _nanomsg as _nn


class MessageTest(unittest.TestCase):

    def test_message(self):

        m = Message()
        self.assertIs(m._control_state, Message.ResourceState.NULL)
        self.assertIs(m._message_state, Message.ResourceState.NULL)
        self.assertEqual(b'', bytes(m.as_memoryview()))

        m.free()
        self.assertIs(m._control_state, Message.ResourceState.NULL)
        self.assertIs(m._message_state, Message.ResourceState.NULL)
        self.assertEqual(b'', bytes(m.as_memoryview()))

        m.adopt_control(b'', False)
        self.assertIs(m._control_state, Message.ResourceState.BORROWER)
        self.assertIs(m._message_state, Message.ResourceState.NULL)
        self.assertEqual(b'', bytes(m.as_memoryview()))

        m.adopt_message(b'', len(b''), False)
        self.assertIs(m._control_state, Message.ResourceState.BORROWER)
        self.assertIs(m._message_state, Message.ResourceState.BORROWER)
        self.assertEqual(b'', bytes(m.as_memoryview()))

        m.free()
        self.assertIs(m._control_state, Message.ResourceState.NULL)
        self.assertIs(m._message_state, Message.ResourceState.NULL)
        self.assertEqual(b'', bytes(m.as_memoryview()))

        m.adopt_control(_nn.nn_allocmsg(10, 0), True)
        self.assertIs(m._control_state, Message.ResourceState.OWNER)
        self.assertIs(m._message_state, Message.ResourceState.NULL)
        self.assertEqual(b'', bytes(m.as_memoryview()))

        m.adopt_message(_nn.nn_allocmsg(10, 0), 0, True)
        self.assertIs(m._control_state, Message.ResourceState.OWNER)
        self.assertIs(m._message_state, Message.ResourceState.OWNER)
        self.assertEqual(b'', bytes(m.as_memoryview()))

        m.free()
        self.assertIs(m._control_state, Message.ResourceState.NULL)
        self.assertIs(m._message_state, Message.ResourceState.NULL)
        self.assertEqual(b'', bytes(m.as_memoryview()))

        m.adopt_control(b'xyz', False)
        m.adopt_message(b'xyz', len(b'xyz'), False)
        self.assertEqual(b'xyz', bytes(m.as_memoryview()))

        self.assertEqual(False, m.disown_control()[1])
        self.assertEqual((3, False), m.disown_message()[1:])


if __name__ == '__main__':
    unittest.main()
