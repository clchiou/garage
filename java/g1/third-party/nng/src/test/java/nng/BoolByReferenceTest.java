package nng;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("fast")
public class BoolByReferenceTest {

    @Test
    public void testBool() {
        BoolByReference ref = new BoolByReference();
        assertFalse(ref.getValue());
        ref.setValue(true);
        assertTrue(ref.getValue());
        ref.setValue(false);
        assertFalse(ref.getValue());
    }
}
