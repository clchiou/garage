package nng;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("fast")
public class ReqRepTest {

    @Test
    public void testReqRep() throws Exception {
        final String url = "inproc://nng.ReqRepTest::testReqRep";
        final byte[][] testdata = {
            {1, 2, 3, 4, 5, 6, 7, 8, 9},
            {15, 14, 13},
            {99, 97, 95, 93, 91},
        };
        final boolean[] success = {false, false};
        Thread thread1 = new Thread(() -> {
            try (Socket socket = Socket.open(Protocols.REP0)) {
                socket.listen(url);
                try (Context context = new Context(socket)) {
                    for (int i = 0; i < testdata.length; i++) {
                        context.send(context.recv());
                    }
                }
            } catch (Exception e) {
                // Make it an unchecked exception.
                throw new RuntimeException(e);
            }
            success[0] = true;
        });
        Thread thread2 = new Thread(() -> {
            try (Socket socket = Socket.open(Protocols.REQ0)) {
                socket.dial(url);
                try (Context context = new Context(socket)) {
                    for (byte[] expect : testdata) {
                        context.send(expect);
                        assertArrayEquals(expect, context.recv());
                    }
                }
            } catch (Exception e) {
                // Make it an unchecked exception.
                throw new RuntimeException(e);
            }
            success[1] = true;
        });
        thread1.setDaemon(true);
        thread2.setDaemon(true);
        thread1.start();
        thread2.start();
        thread1.join(1000);
        thread2.join(1000);
        assertFalse(thread1.isAlive());
        assertFalse(thread2.isAlive());
        assertTrue(success[0]);
        assertTrue(success[1]);
    }
}
