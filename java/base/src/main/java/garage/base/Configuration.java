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
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Stream;

/** Represent configuration entries in a tree. */
public abstract class Configuration {

    @SuppressWarnings("unchecked")
    private static <T> T checkType(Class<T> cls, Object value) {
        Preconditions.checkArgument(
            cls.isInstance(value),
            "Not %s typed: %s", cls, value
        );
        return (T) value;
    }

    private Configuration parent = null;

    public Optional<Configuration> getParent() {
        return Optional.ofNullable(parent);
    }

    private void setParent(Configuration parent) {
        this.parent = parent;
    }

    @VisibleForTesting
    abstract Stream children();

    @SuppressWarnings("unchecked")
    private Iterator<Configuration> childConfigs() {
        return ((Stream) children())
            .filter((child) -> child instanceof Configuration)
            .iterator();
    }

    public <T> T getOrThrow(String path, Class<T> cls) {
        return get(path, cls).orElseThrow(() -> new IllegalArgumentException(
            "cannot get config entry: " + path));
    }

    public <T> Optional<T> get(String path, Class<T> cls) {
        return get(EntryPath.parse(path), cls);
    }

    public <T> Optional<T> get(EntryPath path, Class<T> cls) {
        return getConfig(path).getChild(path.getBase(), cls);
    }

    public abstract <T> Optional<T> getChild(String name, Class<T> cls);
    public abstract <T> Optional<T> getChild(int index, Class<T> cls);

    @VisibleForTesting
    <T> void set(String path, T value) {
        set(EntryPath.parse(path), value);
    }

    private <T> void set(EntryPath path, T value) {
        getConfig(path).setChild(path.getBase(), value);
    }

    abstract <T> void setChild(String name, T value);

    @VisibleForTesting
    void remove(String path) {
        remove(EntryPath.parse(path));
    }

    private void remove(EntryPath path) {
        getConfig(path).removeChild(path.getBase());
    }

    abstract <T> void removeChild(String name);

    private Configuration getConfig(EntryPath path) {
        Configuration config = this;
        for (String key : path.getParent()) {
            config = config.getChild(key, Configuration.class)
                .orElseThrow(() -> new AssertionError(
                    "Entry not found: path=%s" + path));
        }
        return config;
    }

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

    private static class MapConfiguration extends Configuration {

        private ImmutableMap<String, Object> children;

        private MapConfiguration(ImmutableMap<String, Object> children) {
            this.children = children;
        }

        @Override
        Stream children() {
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
        public <T> Optional<T> getChild(int index, Class<T> cls) {
            return getChild(String.valueOf(index), cls);
        }

        @Override
        <T> void setChild(String name, T value) {
            final ImmutableMap.Builder<String, Object> builder =
                ImmutableMap.builder();
            if (children.containsKey(name)) {
                children.forEach((n, v) -> {
                    builder.put(n, n.equals(name) ? value : v);
                });
            } else {
                builder.putAll(children).put(name, value);
            }
            children = builder.build();
        }

        @Override
        void removeChild(String name) {
            Preconditions.checkArgument(children.containsKey(name));
            final ImmutableMap.Builder<String, Object> builder =
                ImmutableMap.builder();
            children.forEach((n, v) -> {
                if (!n.equals(name)) {
                    builder.put(n, v);
                }
            });
            children = builder.build();
        }
    }

    private static class ListConfiguration extends Configuration {

        private ImmutableList<Object> children;

        private ListConfiguration(ImmutableList<Object> children) {
            this.children = children;
        }

        @Override
        Stream children() {
            return children.stream();
        }

        @Override
        public <T> Optional<T> getChild(String name, Class<T> cls) {
            int index;
            try {
                index = Integer.parseInt(name);
            } catch (NumberFormatException e) {
                return Optional.empty();
            }
            return getChild(index, cls);
        }

        @Override
        public <T> Optional<T> getChild(int index, Class<T> cls) {
            if (!(0 <= index && index < children.size())) {
                return Optional.empty();
            }
            Object value = children.get(index);
            return Optional.of(checkType(cls, value));
        }

        @Override
        <T> void setChild(String name, T value) {
            int i = Integer.parseInt(name);
            Preconditions.checkElementIndex(i, children.size());
            children = ImmutableList.builder()
                .addAll(children.subList(0, i))
                .add(value)
                .addAll(children.subList(i + 1, children.size()))
                .build();
        }

        @Override
        void removeChild(String name) {
            int i = Integer.parseInt(name);
            Preconditions.checkElementIndex(i, children.size());
            children = ImmutableList.builder()
                .addAll(children.subList(0, i))
                .addAll(children.subList(i + 1, children.size()))
                .build();
        }
    }

    // Initialize Configuration object from command-line.

    public static class Args extends Application.Args {

        @Option(name = "--config",
                usage = "provide config file path")
        public Path configPath;

        @Option(name = "--config-overwrite",
                usage = "overwrite config entry")
        public Map<String, String> configOverwrites;
    }

    private static boolean isCollectionType(Object value) {
        return (value instanceof Map) || (value instanceof List);
    }

    public static Configuration parse(Args args) throws IOException {
        Yaml yaml = new Yaml();

        Configuration config;
        if (args.configPath != null) {
            Preconditions.checkArgument(
                MoreFiles.isReadableFile(args.configPath),
                "Not a readable file: %s", args.configPath
            );
            try (InputStream input = Files.newInputStream(args.configPath)) {
                Object collection = yaml.load(input);
                Preconditions.checkArgument(
                    isCollectionType(collection),
                    "Not collection value: %s", collection
                );
                config = parseCollection(collection);
            }
        } else {
            config = new MapConfiguration(ImmutableMap.of());
        }

        if (args.configOverwrites != null) {
            args.configOverwrites.forEach((path, yamlText) -> {
                Object value = yaml.load(yamlText);
                if (value == null) {
                    config.remove(path);
                } else {
                    // For simplicity, we only allow primitive overwrite
                    // at the moment.
                    Preconditions.checkArgument(
                        !isCollectionType(value),
                        "Not primitive overwrite value: %s", value
                    );
                    config.set(path, value);
                }
            });
        }

        return config;
    }

    @SuppressWarnings("unchecked")
    @VisibleForTesting
    static Object parseValue(Object object) {
        Preconditions.checkNotNull(object);
        if (object instanceof Map) {
            Map map = (Map) object;
            Preconditions.checkArgument(
                map.keySet().stream().allMatch((key) -> key instanceof String),
                "Invalid key type: %s", map
            );
            return parseMap(map);
        } else if (object instanceof List) {
            return parseList((List<Object>) object);
        } else {
            return object;
        }
    }

    private static Configuration parseCollection(Object object) {
        Preconditions.checkState(
            isCollectionType(object),
            "Not collection value: %s", object
        );
        return (Configuration) parseValue(object);
    }

    private static Configuration parseMap(Map<String, Object> map) {
        ImmutableMap.Builder<String, Object> builder = ImmutableMap.builder();
        map.forEach((key, value) -> {
            builder.put(key, parseValue(value));
        });
        Configuration config = new MapConfiguration(builder.build());
        setParentToChildren(config);
        return config;
    }

    private static Configuration parseList(List<Object> list) {
        Configuration config = new ListConfiguration(ImmutableList.builder()
            .addAll(list.stream().map(Configuration::parseValue).iterator())
            .build()
        );
        setParentToChildren(config);
        return config;
    }

    private static void setParentToChildren(Configuration config) {
        config.childConfigs().forEachRemaining((child) -> {
            child.setParent(config);
        });
    }
}
