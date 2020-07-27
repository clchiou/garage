package g1.base;

import com.google.common.collect.Lists;
import org.kohsuke.args4j.Option;

import java.nio.file.Path;
import java.util.List;

/**
 * Helper class for defining a {@code --config-file} option and a
 * {@code --config} option.
 * <p>
 * This is optional; you can use {@link ConfigurationLoader} without
 * this helper class.
 */
public abstract class ConfiguredApp extends Application {
    @Option(
        name = "--config-path",
        usage = "add config file path"
    )
    public List<Path> configPaths = Lists.newArrayList();

    @Option(
        name = "--config",
        usage = "add config entry X=Y"
    )
    public List<String> configs = Lists.newArrayList();

    public void loadConfigs(List<String> namespaces) {
        ConfigurationLoader loader = new ConfigurationLoader(namespaces);
        loader.loadFromFiles(configPaths);
        loader.loadFromArgs(configs);
    }
}
