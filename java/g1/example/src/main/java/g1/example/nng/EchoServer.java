package g1.example.nng;

import com.google.common.collect.ImmutableList;
import g1.base.Application;
import g1.base.Configuration;
import g1.base.ConfigurationLoader;
import g1.base.ConfiguredApp;
import nng.Context;
import nng.Options;
import nng.Protocols;
import nng.Socket;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class EchoServer extends ConfiguredApp {
    private static final Logger LOG = LoggerFactory.getLogger(
        EchoServer.class
    );

    @Configuration
    public static String url = "tcp://127.0.0.1:9000";

    public static void main(String[] args) {
        Application.main(new EchoServer(), args);
    }

    @Override
    public void run() throws Exception {
        new ConfigurationLoader(ImmutableList.of("g1")).load(configPaths);
        LOG.atInfo().addArgument(url).log("listen: {}", url);
        try (Socket socket = Socket.open(Protocols.REP0)) {
            LOG.atInfo()
                .addArgument(socket.get(Options.NNG_OPT_PROTONAME))
                .log("protocol: {}");
            socket.listen(url);
            try (Context context = new Context(socket)) {
                byte[] request = context.recv();
                LOG.atInfo()
                    .addArgument(Arrays.toString(request))
                    .addArgument(new String(request, StandardCharsets.UTF_8))
                    .log("recv: {} aka \"{}\"");
                context.send(request);
            }
        }
    }
}
