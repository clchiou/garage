package g1.msg;

import org.capnproto.MessageBuilder;
import org.capnproto.MessageReader;

/**
 * Request handler interface.
 */
public interface Handler {
    void handle(MessageReader request, MessageBuilder response) throws Exception;
}
