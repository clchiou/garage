package g1.example.msg;

import g1.example.Books.BookRequest;
import g1.example.Books.BookResponse;
import g1.msg.Capnp;
import org.capnproto.MessageBuilder;
import org.capnproto.MessageReader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.zeromq.SocketType;
import org.zeromq.ZContext;
import org.zeromq.ZMQ;

public class BookClient {
    private static final Logger LOG = LoggerFactory.getLogger(BookClient.class);

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.printf("usage: %s url%n", BookClient.class.getSimpleName());
            System.exit(1);
            return;
        }

        try (ZContext context = new ZContext()) {
            context.setLinger(0); // Do NOT block the program exit!

            try (ZMQ.Socket socket = context.createSocket(SocketType.REQ)) {
                socket.connect(args[0]);

                MessageBuilder request = new MessageBuilder();
                request.initRoot(BookRequest.factory).initArgs().initListBooks();
                socket.send(Capnp.encode(request));

                MessageReader response = Capnp.decode(socket.recv());
                BookResponse.Reader bookResponse = response.getRoot(BookResponse.factory);
                LOG.atInfo().addArgument(bookResponse).log("response: {}");
            }
        }
    }
}
