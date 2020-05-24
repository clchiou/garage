package nng;

import com.sun.jna.Native;
import com.sun.jna.ptr.ByReference;

/**
 * Map {@code bool*} to a reference type.
 * <p>
 * We assume the native bool type use 1 byte for storage.
 * <p>
 * (I do not know why JNA does not have this.)
 */
public class BoolByReference extends ByReference {
    static {
        if (Native.BOOL_SIZE != 1) {
            throw new AssertionError("expect sizeof(bool) == 1");
        }
    }

    public BoolByReference() {
        this(false);
    }

    public BoolByReference(boolean value) {
        super(Native.BOOL_SIZE);
        setValue(value);
    }

    public boolean getValue() {
        return getPointer().getByte(0L) != 0;
    }

    public void setValue(boolean value) {
        getPointer().setByte(0L, value ? (byte) 1 : (byte) 0);
    }
}
