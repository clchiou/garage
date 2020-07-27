package g1.example;

import com.google.common.collect.ImmutableList;
import g1.base.Application;
import g1.base.Configuration;
import g1.base.ConfiguredApp;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class HelloWorld extends ConfiguredApp {
    private static final Logger LOG = LoggerFactory.getLogger(
        HelloWorld.class
    );

    @Configuration
    public static String name = "world";

    public static void main(String[] args) {
        Application.main(new HelloWorld(), args);
    }

    @Override
    public void run() throws Exception {
        loadConfigs(ImmutableList.of("g1"));
        // Use {@code -Dorg.slf4j.simpleLogger.defaultLogLevel=...} on
        // command-line to change the default logging level (info).
        LOG.atInfo().addArgument(name).log("Hello, {}!");
    }
}
