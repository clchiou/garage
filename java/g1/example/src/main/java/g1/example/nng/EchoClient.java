package g1.example.nng;

import com.google.common.collect.ImmutableList;
import g1.base.Application;
import g1.base.Configuration;
import g1.base.ConfiguredApp;
import nng.Context;
import nng.Options;
import nng.Protocols;
import nng.Socket;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class EchoClient extends ConfiguredApp {
    private static final Logger LOG = LoggerFactory.getLogger(
        EchoClient.class
    );

    @Configuration
    public static String url = "tcp://127.0.0.1:9000";

    @Configuration
    public static String message = "Hello, world!";

    public static void main(String[] args) {
        Application.main(new EchoClient(), args);
    }

    @Override
    public void run() throws Exception {
        loadConfigs(ImmutableList.of("g1"));
        LOG.atInfo().addArgument(url).log("connect: {}", url);
        try (Socket socket = Socket.open(Protocols.REQ0)) {
            LOG.atInfo()
                .addArgument(socket.get(Options.NNG_OPT_PROTONAME))
                .log("protocol: {}");
            socket.dial(url);
            socket.set(Options.NNG_OPT_SENDTIMEO, 4000);
            try (Context context = new Context(socket)) {
                context.send(message.getBytes(StandardCharsets.UTF_8));
                byte[] response = context.recv();
                LOG.atInfo()
                    .addArgument(Arrays.toString(response))
                    .addArgument(new String(response, StandardCharsets.UTF_8))
                    .log("recv: {} aka \"{}\"");
            }
        }
    }
}
