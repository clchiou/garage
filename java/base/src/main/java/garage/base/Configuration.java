package garage.base;

import com.google.common.annotations.VisibleForTesting;
import com.google.common.base.Joiner;
import com.google.common.base.Preconditions;
import com.google.common.base.Splitter;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import org.kohsuke.args4j.Option;
import org.yaml.snakeyaml.Yaml;

import javax.annotation.Nonnull;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collection;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Stream;

/** Represent configuration entries in a tree. */
public abstract class Configuration {

    @SuppressWarnings("unchecked")
    protected static <T> T checkType(Class<T> cls, Object value) {
        Preconditions.checkArgument(
            cls.isInstance(value),
            "Not %s typed: %s", cls, value
        );
        return (T)value;
    }

    private Configuration parent = null;

    public Optional<Configuration> getParent() {
        return Optional.ofNullable(parent);
    }

    private void setParent(Configuration parent) {
        this.parent = parent;
    }

    protected abstract Stream children();

    @SuppressWarnings("unchecked")
    private Iterator<Configuration> childConfigs() {
        return ((Stream)children())
            .filter((child) -> child instanceof Configuration)
            .iterator();
    }

    public <T> Optional<T> get(String path, Class<T> cls) {
        return get(EntryPath.parse(path), cls);
    }

    public <T> Optional<T> get(EntryPath path, Class<T> cls) {
        Configuration config = this;
        for (String key : path.getParent()) {
            config = config.getChild(key, Configuration.class)
                .orElseThrow(() -> new AssertionError(
                    "Entry not found: path=%s" + path));
        }
        return config.getChild(path.getBase(), cls);
    }

    public abstract <T> Optional<T> getChild(String name, Class<T> cls);

    private <T> void set(String path, T value) {
        set(EntryPath.parse(path), value);
    }

    private <T> void set(EntryPath path, T value) {
        Configuration config = this;
        for (String key : path.getParent()) {
            config = config.getChild(key, Configuration.class)
                .orElseThrow(() -> new AssertionError(
                    "Entry not found: path=%s" + path));
        }
        config.setChild(path.getBase(), value);
    }

    protected abstract <T> void setChild(String name, T value);

    // Define helper class and implement the interface.

    public static class EntryPath implements Iterable<String> {

        private static final Joiner JOINER = Joiner.on('.');
        private static final Splitter SPLITTER = Splitter.on('.');

        public static EntryPath parse(String path) {
            return new EntryPath(ImmutableList.copyOf(SPLITTER.split(path)));
        }

        private final ImmutableList<String> keys;

        @VisibleForTesting
        EntryPath(ImmutableList<String> keys) {
            Preconditions.checkArgument(
                keys.stream().noneMatch(String::isEmpty),
                "Invalid path: %s", keys
            );
            this.keys = keys;
        }

        public EntryPath getParent() {
            Preconditions.checkState(!keys.isEmpty());
            return new EntryPath(keys.subList(0, keys.size() - 1));
        }

        public String getBase() {
            Preconditions.checkState(!keys.isEmpty());
            return keys.get(keys.size() - 1);
        }

        public boolean isEmpty() {
            return keys.isEmpty();
        }

        public int size() {
            return keys.size();
        }

        @Override
        @Nonnull
        public Iterator<String> iterator() {
            return keys.iterator();
        }

        public String get(int i) {
            return keys.get(i);
        }

        @Override
        public String toString() {
            return JOINER.join(keys);
        }
    }

    @VisibleForTesting
    static class MapConfiguration extends Configuration {

        private ImmutableMap<String, Object> children;

        @VisibleForTesting
        MapConfiguration(ImmutableMap<String, Object> children) {
            this.children = children;
        }

        @Override
        public Stream children() {
            return children.values().stream();
        }

        @Override
        public <T> Optional<T> getChild(String name, Class<T> cls) {
            Object value = children.get(name);
            if (value == null) {
                return Optional.empty();
            }
            return Optional.of(checkType(cls, value));
        }

        @Override
        protected <T> void setChild(String name, T value) {
            children = ImmutableMap.<String, Object>builder()
                .putAll(children)
                .put(name, value)
                .build();
        }
    }

    @VisibleForTesting
    static class ListConfiguration extends Configuration {

        private ImmutableList<Object> children;

        @VisibleForTesting
        ListConfiguration(ImmutableList<Object> children) {
            this.children = children;
        }

        @Override
        public Stream children() {
            return children.stream();
        }

        @Override
        public <T> Optional<T> getChild(String name, Class<T> cls) {
            Object value = children.get(Integer.parseInt(name));
            return Optional.of(checkType(cls, value));
        }

        @Override
        protected <T> void setChild(String name, T value) {
            int i = Integer.parseInt(name);
            Preconditions.checkArgument(0 <= i && i < children.size());
            children = ImmutableList.builder()
                .addAll(children.subList(0, i))
                .add(value)
                .addAll(children.subList(i + 1, children.size()))
                .build();
        }
    }

    // Initialize Configuration object from command-line.

    public static class Args extends Application.Args {

        @Option(name = "--config-file",
                usage = "provide config file path")
        public Path configFilePath;

        @Option(name = "--config-overwrite",
                usage = "overwrite config entry")
        public Map<String, String> configOverwrites;
    }

    public static Configuration parse(Args args) throws IOException {
        Yaml yaml = new Yaml();

        Configuration config;
        if (args.configFilePath != null) {
            Preconditions.checkArgument(
                MoreFiles.isReadableFile(args.configFilePath),
                "Not a readable file: %s", args.configFilePath
            );
            try (InputStream input =
                    Files.newInputStream(args.configFilePath)) {
                Collection collection = yaml.loadAs(input, Collection.class);
                config = parse(collection);
            }
        } else {
            config = new MapConfiguration(ImmutableMap.of());
        }

        if (args.configOverwrites != null) {
            args.configOverwrites.forEach((path, yamlText) -> {
                config.set(path, yaml.load(yamlText));
            });
        }

        return config;
    }

    @SuppressWarnings("unchecked")
    @VisibleForTesting
    static Configuration parse(Collection collection) {
        if (collection instanceof Map) {
            Map map = (Map<String, Object>)collection;
            Preconditions.checkArgument(
                map.keySet().stream().allMatch((key) -> key instanceof String),
                "Invalid configuration key type: %s", map
            );
            return parse(map);
        } else if (collection instanceof List) {
            return parse((List<Object>)collection);
        } else {
            throw new AssertionError(
                "Unknown collection type: " + collection);
        }
    }

    @VisibleForTesting
    static Configuration parse(Map<String, Object> map) {
        ImmutableMap.Builder<String, Object> builder = ImmutableMap.builder();
        map.forEach((key, value) -> {
            builder.put(key, parseValue(value));
        });
        Configuration config = new MapConfiguration(builder.build());
        setParentToChildren(config);
        return config;
    }

    @VisibleForTesting
    static Configuration parse(List<Object> list) {
        Configuration config = new ListConfiguration(ImmutableList.builder()
            .addAll(list.stream().map(Configuration::parseValue).iterator())
            .build()
        );
        setParentToChildren(config);
        return config;
    }

    private static Object parseValue(Object value) {
        return value instanceof Collection ? parse((Collection)value) : value;
    }

    private static void setParentToChildren(Configuration config) {
        config.childConfigs().forEachRemaining((child) -> {
            child.setParent(config);
        });
    }
}
