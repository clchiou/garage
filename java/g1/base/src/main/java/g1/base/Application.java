package g1.base;

import org.kohsuke.args4j.CmdLineException;
import org.kohsuke.args4j.CmdLineParser;
import org.kohsuke.args4j.Option;

import java.io.PrintStream;

/**
 * Base application class.
 * <p>
 * User should extend this class to (1) add command-line options, and
 * (2) override the application main function {@code run}.
 */
public abstract class Application {

    @Option(
        name = "-h",
        aliases = {"--help"},
        help = true,
        usage = "print this message"
    )
    public boolean help = false;

    public static <T extends Application> void main(
        T application,
        String[] args
    ) {
        if (!parse(application, args, System.err)) {
            System.exit(1);
        }
        try {
            application.run();
        } catch (Exception e) {
            e.printStackTrace();
            System.exit(1);
        }
    }

    private static <T extends Application> boolean parse(
        T application,
        String[] args,
        PrintStream output
    ) {
        CmdLineParser parser = new CmdLineParser(application);
        try {
            parser.parseArgument(args);
        } catch (CmdLineException e) {
            output.println(e.getMessage());
            parser.printUsage(output);
            return false;
        }

        if (application.help) {
            // Restore application.help to its default value so that
            // printUsage() may show the correct value.
            application.help = false;
            parser.printUsage(output);
            return false;
        }

        return true;
    }

    /**
     * The main function that user should override.
     */
    public abstract void run() throws Exception;
}
