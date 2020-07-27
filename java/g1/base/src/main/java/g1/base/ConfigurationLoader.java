package g1.base;

import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableTable;
import com.google.common.collect.Table;
import org.reflections.Reflections;
import org.reflections.scanners.FieldAnnotationsScanner;
import org.reflections.util.ClasspathHelper;
import org.reflections.util.ConfigurationBuilder;
import org.reflections.util.FilterBuilder;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.yaml.snakeyaml.Yaml;

import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Load configuration data from files.
 * <p>
 * NOTE: This has one major difference from our Python {@code parts}
 * that this supports declaring configuration entries on only class
 * level, whereas our Python {@code parts} supports declaring on both
 * class and instance level.
 */
public class ConfigurationLoader {
    private static final Logger LOG = LoggerFactory.getLogger(
        ConfigurationLoader.class
    );

    private final Table<String, String, Field> fields;

    public ConfigurationLoader(List<String> namespaces) {
        Reflections reflections = new Reflections(
            new ConfigurationBuilder()
                .filterInputsBy(
                    new FilterBuilder()
                        .includePackage(namespaces.toArray(new String[0]))
                )
                .setUrls(
                    namespaces.stream()
                        .map(ClasspathHelper::forPackage)
                        .flatMap(Collection::stream)
                        .collect(Collectors.toList())
                )
                .setScanners(new FieldAnnotationsScanner())
        );
        ImmutableTable.Builder<String, String, Field> fieldsBuilder =
            ImmutableTable.builder();
        for (
            Field field :
            reflections.getFieldsAnnotatedWith(Configuration.class)
        ) {
            if (field.getAnnotation(Configuration.class) == null) {
                continue;
            }
            String className = field.getDeclaringClass().getCanonicalName();
            String fieldName = field.getName();
            int modifiers = field.getModifiers();
            if (
                Modifier.isFinal(modifiers) ||
                    !Modifier.isStatic(modifiers) ||
                    !Modifier.isPublic(modifiers)
            ) {
                LOG.atWarn()
                    .addArgument(className)
                    .addArgument(fieldName)
                    .log("skip non public static field: {}:{}");
                continue;
            }
            LOG.atInfo()
                .addArgument(className)
                .addArgument(fieldName)
                .log("add public static field: {}:{}");
            fieldsBuilder.put(className, fieldName, field);
        }
        fields = fieldsBuilder.build();
    }

    public void loadFromFiles(List<Path> configPaths) {
        Yaml yaml = new Yaml();
        for (Path configPath : configPaths) {
            loadOne(yaml, configPath);
        }
    }

    private void loadOne(Yaml yaml, Path configPath) {
        LOG.atInfo().addArgument(configPath).log("load config from: {}");
        Map<String, Map<String, Object>> config;
        try (InputStream input = Files.newInputStream(configPath)) {
            config = yaml.load(input);
        } catch (ClassCastException | IOException e) {
            LOG.atWarn()
                .addArgument(configPath)
                .setCause(e)
                .log("fail to load config file: {}");
            return;
        }
        if (config == null) {
            LOG.atWarn().addArgument(configPath).log("empty config file: {}");
            return;
        }
        for (
            Map.Entry<String, Map<String, Object>> entry :
            config.entrySet()
        ) {
            try {
                loadEntry(entry.getKey(), entry.getValue());
            } catch (ClassCastException e) {
                LOG.atWarn()
                    .addArgument(configPath)
                    .addArgument(entry.getKey())
                    .log("skip invalid entry in {}: key={}");
            }
        }
    }

    public void loadFromArgs(List<String> configs) {
        Yaml yaml = new Yaml();
        for (String config : configs) {
            int i = config.indexOf(':');
            if (i < 0) {
                LOG.atWarn()
                    .addArgument(config)
                    .log("skip invalid command-line entry: {}");
                continue;
            }
            int j = config.indexOf('=', i);
            if (j < 0) {
                LOG.atWarn()
                    .addArgument(config)
                    .log("skip invalid command-line entry: {}");
                continue;
            }
            String className = config.substring(0, i);
            String name = config.substring(i + 1, j);
            String value = config.substring(j + 1);
            loadEntry(className, ImmutableMap.of(name, yaml.load(value)));
        }
    }

    private void loadEntry(String className, Map<String, Object> values) {
        for (Map.Entry<String, Object> entry : values.entrySet()) {
            String fieldName;
            try {
                fieldName = entry.getKey();
            } catch (ClassCastException e) {
                LOG.atWarn()
                    .addArgument(className)
                    .addArgument(entry.getKey())
                    .log("skip non-string key in {}: {}");
                continue;
            }
            Field field = fields.get(className, fieldName);
            if (field == null) {
                LOG.atWarn()
                    .addArgument(className)
                    .addArgument(fieldName)
                    .log("undefined field: {}:{}");
                continue;
            }
            Object value = entry.getValue();
            LOG.atInfo()
                .addArgument(className)
                .addArgument(fieldName)
                .addArgument(value)
                .log("set field: {}:{} = {}");
            try {
                field.set(field.getDeclaringClass(), value);
            } catch (IllegalAccessException | IllegalArgumentException e) {
                LOG.atWarn()
                    .addArgument(className)
                    .addArgument(fieldName)
                    .setCause(e)
                    .log("fail to set field: {}:{}");
            }
        }
    }
}
