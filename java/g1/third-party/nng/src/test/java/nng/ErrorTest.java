package nng;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.fail;

@Tag("fast")
public class ErrorTest {

    @Test
    public void testCheckPass() {
        Error.check(0);
    }

    @Test
    public void testCheckError() {
        try {
            Error.check(Error.NNG_EINTR);
            fail("expect Error thrown");
        } catch (Error e) {
            assertEquals(e.getErrno(), Error.NNG_EINTR);
        }
        try {
            Error.check(/* no such errno */ -1);
            fail("expect Error thrown");
        } catch (Error e) {
            assertEquals(e.getErrno(), -1);
        }
    }
}
