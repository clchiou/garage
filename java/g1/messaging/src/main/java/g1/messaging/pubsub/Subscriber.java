package g1.messaging.pubsub;

import org.capnproto.MessageReader;

/**
 * Subscriber interface.
 */
public interface Subscriber {
    void consume(MessageReader message) throws Exception;
}
