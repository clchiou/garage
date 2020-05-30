package nng;

import com.sun.jna.Pointer;
import com.sun.jna.ptr.PointerByReference;

import static nng.Error.check;
import static nng.Nng.NNG;

/* package private */ class Utils {

    /* package private */
    static Pointer allocAio() {
        PointerByReference aio = new PointerByReference();
        check(NNG.nng_aio_alloc(aio, null, null));
        return aio.getValue();
    }

    /* package private */
    static Pointer allocMessage() {
        PointerByReference message = new PointerByReference();
        check(NNG.nng_msg_alloc(message, 0));
        return message.getValue();
    }
}
