package nanomsg;

import com.google.common.base.Preconditions;
import com.sun.jna.Pointer;

import java.nio.ByteBuffer;

import static nanomsg.Error.check;
import static nanomsg.Nanomsg.NANOMSG;

public class Message implements AutoCloseable {

    private Pointer message;
    private final int size;

    Message(Pointer message, int size) {
        this.message = message;
        this.size = size;
    }

    @Override
    public synchronized void close() {
        check(NANOMSG.nn_freemsg(message));
        message = null;
    }

    @Override
    protected void finalize() throws Throwable {
        close();
    }

    public synchronized ByteBuffer getDirectByteBuffer() {
        Preconditions.checkState(message != null);
        return message.getByteBuffer(0, size);
    }

    public synchronized ByteBuffer getByteBuffer() {
        Preconditions.checkState(message != null);

        ByteBuffer buffer = getDirectByteBuffer();

        ByteBuffer copy = ByteBuffer.allocate(buffer.remaining());
        copy.put(buffer).flip();

        return copy;
    }
}
