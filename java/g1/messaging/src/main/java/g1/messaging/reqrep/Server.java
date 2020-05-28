package g1.messaging.reqrep;

import org.capnproto.MessageBuilder;
import org.capnproto.MessageReader;

/**
 * Interface of a reqrep server.
 */
public interface Server {
    void serve(
        MessageReader request,
        MessageBuilder response
    ) throws Exception;
}
