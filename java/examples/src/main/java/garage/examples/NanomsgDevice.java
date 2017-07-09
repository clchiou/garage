package garage.examples;

import com.google.common.base.Preconditions;
import org.kohsuke.args4j.Option;
import org.kohsuke.args4j.spi.StringArrayOptionHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.List;

import nanomsg.Domain;
import nanomsg.Message;
import nanomsg.Protocol;
import nanomsg.Socket;

import garage.base.Application;

public class NanomsgDevice {

    private static final Logger LOG =
        LoggerFactory.getLogger(NanomsgDevice.class);

    private enum Mode {
        device, client, server;
    }

    private static class Args extends Application.Args {

        @Option(name = "--mode", required = true, usage = "set app mode")
        private Mode mode;

        @Option(
            name = "--urls",
            required = true,
            handler = StringArrayOptionHandler.class,
            usage = "provide endpoint URLs"
        )
        private List<String> urls;

        @Option(name = "--message", usage = "send this message")
        private String message;
    }

    public static void main(String[] args) {
        Application.run(args, new Args(), NanomsgDevice::main);
    }

    private static void main(Args args) throws Exception {
        switch (args.mode) {
            case device:
                Preconditions.checkArgument(args.urls.size() == 2);
                device(args.urls.get(0), args.urls.get(1));
                break;
            case client:
                Preconditions.checkArgument(args.urls.size() == 1);
                Preconditions.checkArgument(args.message != null);
                client(args.urls.get(0), args.message);
                break;
            case server:
                Preconditions.checkArgument(args.urls.size() == 1);
                server(args.urls.get(0));
                break;
            default:
                throw new AssertionError();
        }
    }

    private static void device(String url1, String url2) {
        try (Socket s1 = new Socket(Domain.AF_SP_RAW, Protocol.NN_REP);
             Socket s2 = new Socket(Domain.AF_SP_RAW, Protocol.NN_REQ)) {
            s1.bind(url1);
            s2.bind(url2);
            LOG.info("device: {} <-> {}", s1, s2);
            Socket.device(s1, s2);
        }
    }

    private static void client(String url, String message) {
        try (Socket socket = new Socket(Domain.AF_SP, Protocol.NN_REQ)) {
            socket.connect(url);

            LOG.info("client: {} <- \"{}\"", socket, message);
            socket.send(encode(message));

            try (Message rep = socket.recv()) {
                LOG.info(
                    "client: {} -> \"{}\"",
                    socket, decode(rep.getByteBuffer())
                );
            }
        }
    }

    private static void server(String url) {
        try (Socket socket = new Socket(Domain.AF_SP, Protocol.NN_REP)) {
            socket.connect(url);
            while (true) {

                String message;
                try (Message req = socket.recv()) {
                    message = decode(req.getByteBuffer());
                }
                LOG.info("server: {} <- \"{}\"", socket, message);

                socket.send(encode(String.format("echo: \"%s\"", message)));

                if (message.equalsIgnoreCase("exit")) {
                    break;
                }
            }
        }
    }

    private static ByteBuffer encode(String message) {
        return ByteBuffer.wrap(message.getBytes(StandardCharsets.UTF_8));
    }

    private static String decode(ByteBuffer message) {
        return new String(
            message.array(),
            message.position(),
            message.remaining(),
            StandardCharsets.UTF_8
        );
    }
}
