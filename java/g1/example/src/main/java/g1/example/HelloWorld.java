package g1.example;

import g1.base.Application;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class HelloWorld extends Application {
    private static final Logger LOG = LoggerFactory.getLogger(
        HelloWorld.class
    );

    public static void main(String[] args) {
        Application.main(new HelloWorld(), args);
    }

    @Override
    public void run() throws Exception {
        // Use {@code -Dorg.slf4j.simpleLogger.defaultLogLevel=...} on
        // command-line to change the default logging level (info).
        LOG.atInfo().log("Hello, world!");
    }
}
