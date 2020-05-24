package nng;

import com.google.common.collect.ImmutableSet;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.fail;

@Tag("fast")
public class OptionsTest {

    @Test
    public void testGet() throws Exception {
        Set<Options> notSupported = ImmutableSet.of(
            Options.NNG_OPT_URL,
            Options.NNG_OPT_TCP_BOUND_PORT,
            Options.NNG_OPT_SUB_SUBSCRIBE,
            Options.NNG_OPT_SUB_UNSUBSCRIBE,
            Options.NNG_OPT_SURVEYOR_SURVEYTIME
        );
        try (Socket socket = Socket.open(Protocols.REQ0)) {
            socket.dial("inproc://nng.OptionsTest::testGet");
            for (Options option : Options.values()) {
                if (notSupported.contains(option)) {
                    try {
                        socket.get(option);
                        fail("expect Error thrown");
                    } catch (Error e) {
                        assertEquals(e.getErrno(), Error.NNG_ENOTSUP);
                    }
                } else {
                    assertNotNull(socket.get(option));
                }
            }
        }
    }

    @Test
    public void testSet() throws Exception {
        try (Socket socket = Socket.open(Protocols.REQ0)) {
            socket.dial("inproc://nng.OptionsTest::testSet");
            try {
                socket.set(Options.NNG_OPT_RAW, true);
                fail("expect IllegalStateException thrown");
            } catch (IllegalStateException e) {
                // As expected.
            }
            int timeout = (Integer) socket.get(Options.NNG_OPT_RECVTIMEO);
            int expect = timeout + 1000;
            socket.set(Options.NNG_OPT_RECVTIMEO, expect);
            assertEquals(socket.get(Options.NNG_OPT_RECVTIMEO), expect);
        }
    }
}
