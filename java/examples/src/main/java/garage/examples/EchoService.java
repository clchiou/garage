package garage.examples;

import com.google.common.base.Preconditions;
import com.google.common.collect.Lists;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.List;

import garage.base.Application;
import garage.base.Configuration;
import garage.base.Configuration.Args;
import garage.messaging.SimpleService;

public class EchoService {

    private EchoService() {
        throw new AssertionError();
    }

    private static ByteBuffer echo(ByteBuffer message) {
        return encode("echo: " + decode(message));
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

    public static void main(String[] args) {
        Application.run(args, new Args(), EchoService::main);
    }

    private static void main(Args args) throws Exception {

        Configuration config = Configuration.parse(args);

        SimpleService service = new SimpleService(config);

        int numHandlers = config.getOrThrow("num_handlers", Integer.class);
        Preconditions.checkArgument(numHandlers >= 1);

        List<SimpleService.Handler> handlers = Lists.newArrayList();
        for (int i = 0; i < numHandlers; i++) {
            handlers.add(EchoService::echo);
        }

        service.start(handlers);

        service.await();
    }
}
