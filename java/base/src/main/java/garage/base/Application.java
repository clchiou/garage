package garage.base;

import org.kohsuke.args4j.CmdLineException;
import org.kohsuke.args4j.CmdLineParser;
import org.kohsuke.args4j.Option;

import java.io.PrintStream;
import java.util.Optional;

public class Application {

    public interface Main<T> {
        void main(T args) throws Exception;
    }

    public static class Args {

        @Option(name = "-h", aliases = {"--help"},
                help = true,
                usage = "print this message")
        public boolean doHelp = false;
    }

    private static <T extends Args> Optional<T> parse(
        String[] args, T instance,
        PrintStream output
    ) {
        CmdLineParser parser = new CmdLineParser(instance);
        try {
            parser.parseArgument(args);
        } catch (CmdLineException e) {
            output.println(e.getMessage());
            parser.printUsage(output);
            return Optional.empty();
        }

        if (instance.doHelp) {
            // Restore instance.doHelp to its default value so that
            // printUsage() may show the correct value.
            instance.doHelp = false;
            parser.printUsage(output);
            return Optional.empty();
        }

        return Optional.of(instance);
    }

    public static <T extends Args> void run(
        String[] args, T instance,
        Main<T> main
    ) {
        System.exit(
            parse(args, instance, System.err)
            .map((T parsedArgs) -> {
                try {
                    main.main(parsedArgs);
                    return 0;
                } catch (Exception exc) {
                    exc.printStackTrace();
                    return 1;
                }
            })
            .orElse(1)
        );
    }

    private Application() {
        throw new AssertionError();
    }
}
