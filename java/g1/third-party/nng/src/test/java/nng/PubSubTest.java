package nng;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("fast")
public class PubSubTest {

    @Test
    public void testPubSub() throws Exception {
        final String url = "inproc://nng.PubSubTest::testPubSub";
        final CountDownLatch barrier = new CountDownLatch(1);
        final boolean[] success = {false, false};
        Thread thread1 = new Thread(() -> {
            try (Socket socket = Socket.open(Protocols.PUB0)) {
                // NOTE: pub0 sockets do not support context.
                socket.listen(url);
                for (byte i = 0; i < 100; i++) {
                    socket.send(new byte[]{i});
                    if (barrier.await(100, TimeUnit.MILLISECONDS)) {
                        break;
                    }
                }
            } catch (Exception e) {
                // Make it an unchecked exception.
                throw new RuntimeException(e);
            }
            success[0] = true;
        });
        Thread thread2 = new Thread(() -> {
            try (Socket socket = Socket.open(Protocols.SUB0)) {
                socket.set(Options.NNG_OPT_SUB_SUBSCRIBE, new byte[0]);
                socket.dial(url);
                // Socket and context have their own, separated
                // subscribed topics.
                byte x = socket.recv()[0];
                for (int i = 0; i < 3; i++) {
                    assertArrayEquals(socket.recv(), new byte[]{++x});
                }
            } catch (Exception e) {
                // Make it an unchecked exception.
                throw new RuntimeException(e);
            } finally {
                barrier.countDown();
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
