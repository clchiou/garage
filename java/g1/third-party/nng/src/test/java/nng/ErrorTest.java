package nng;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Tag("fast")
public class ErrorTest {

    @Test
    public void testCheckPass() {
        Error.check(0);
    }

    @Test
    public void testCheckError() {
        Error e;
        e = assertThrows(Error.class, () -> {
            Error.check(Error.NNG_EINTR);
        });
        assertEquals(Error.NNG_EINTR, e.getErrno());
        e = assertThrows(Error.class, () -> {
            Error.check(/* no such errno */ -1);
        });
        assertEquals(-1, e.getErrno());
    }
}
