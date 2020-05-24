package nng;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("fast")
public class ReqRepTest {

    @Test
    public void testReq() throws Exception {
        final String url = "inproc://nng.ReqRepTest::testReq";
        final boolean[] success = {false};
        Thread thread = new Thread(() -> {
            try (Socket socket = Socket.open(Protocols.REP0)) {
                socket.listen(url);
                try (Context context = new Context(socket)) {
                    context.send(context.recv());
                }
            } catch (Exception e) {
                // Make it an unchecked exception.
                throw new RuntimeException(e);
            }
            success[0] = true;
        });
        thread.setDaemon(true);
        thread.start();
        try (Socket socket = Socket.open(Protocols.REQ0)) {
            socket.dial(url);
            try (Context context = new Context(socket)) {
                byte[] expect = {1, 2, 3, 4, 5, 6, 7, 8, 9};
                context.send(expect);
                byte[] actual = context.recv();
                assertArrayEquals(actual, expect);
            }
        } finally {
            thread.join(4000);
            assertFalse(thread.isAlive());
        }
        assertTrue(success[0]);
    }

    @Test
    public void testRep() throws Exception {
        final String url = "inproc://nng.ReqRepTest::testRep";
        final boolean[] success = {false};
        Thread thread = new Thread(() -> {
            try (Socket socket = Socket.open(Protocols.REQ0)) {
                socket.dial(url);
                try (Context context = new Context(socket)) {
                    byte[] expect = {1, 2, 3, 4, 5, 6, 7, 8, 9};
                    context.send(expect);
                    byte[] actual = context.recv();
                    assertArrayEquals(actual, expect);
                }
            } catch (Exception e) {
                // Make it an unchecked exception.
                throw new RuntimeException(e);
            }
            success[0] = true;
        });
        thread.setDaemon(true);
        thread.start();
        try (Socket socket = Socket.open(Protocols.REP0)) {
            socket.listen(url);
            try (Context context = new Context(socket)) {
                context.send(context.recv());
            }
        } finally {
            thread.join(4000);
            assertFalse(thread.isAlive());
        }
        assertTrue(success[0]);
    }
}
