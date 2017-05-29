package garage.base;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.util.Optional;
import java.util.function.Supplier;

import static org.junit.jupiter.api.Assertions.*;

@Tag("fast")
public class ConfigurationTest {

    @Test
    public void testEntryPath() {
        Configuration.EntryPath path;

        path = Configuration.EntryPath.parse("part1");
        assertEquals(1, path.size());
        assertEquals("part1", path.get(0));
        assertEquals("part1", path.toString());

        path = Configuration.EntryPath.parse("p/a/r/t/1.p-a-r-t-2");
        assertEquals(2, path.size());
        assertEquals("p/a/r/t/1", path.get(0));
        assertEquals("p-a-r-t-2", path.get(1));
        assertEquals("p/a/r/t/1.p-a-r-t-2", path.toString());

        Throwable exc;

        exc = assertThrows(
            IllegalArgumentException.class,
            () -> Configuration.EntryPath.parse("")
        );
        assertEquals("Invalid path: []", exc.getMessage());

        exc = assertThrows(
            IllegalArgumentException.class,
            () -> Configuration.EntryPath.parse("a..b")
        );
        assertEquals("Invalid path: [a, , b]", exc.getMessage());
    }

    @Test
    public void testEmptyConfiguration() {
        Configuration config;

        config = (Configuration) Configuration.parseValue(ImmutableMap.of());
        assertFalse(config.getParent().isPresent());

        config = (Configuration) Configuration.parseValue(ImmutableList.of());
        assertFalse(config.getParent().isPresent());
    }

    @Test
    public void testConfiguration() {
        Configuration root = (Configuration) Configuration.parseValue(
            ImmutableMap.of(
                "int-key", 1,
                "dict-key", ImmutableMap.of(
                    "p", "string-value"
                ),
                "list-key", ImmutableList.of(
                    "some-str",
                    ImmutableMap.of(
                        "x", ImmutableMap.of()
                    )
                )
            )
        );

        assertFalse(root.getParent().isPresent());

        assertFalse(root.getChild("x", Object.class).isPresent());
        assertFalse(root.getChild(0, Object.class).isPresent());

        assertFalse(root.get("dict-key.x", Object.class).isPresent());
        assertFalse(root.get("list-key.-1", Object.class).isPresent());
        assertFalse(root.get("list-key.2", Object.class).isPresent());
        assertFalse(root.get("list-key.x", Object.class).isPresent());

        Throwable exc = assertThrows(
            IllegalArgumentException.class,
            () -> root.get("int-key", Configuration.class)
        );
        assertTrue(exc.getMessage().matches("Not .* typed: 1"));

        Optional<Integer> i = root.get("int-key", Integer.class);
        assertEquals(Integer.valueOf(1), i.orElse(null));

        Configuration config;

        config = root.get("dict-key", Configuration.class).orElse(null);
        assertNotNull(config);
        assertEquals(root, config.getParent().orElse(null));
        assertEquals(
            "string-value",
            config.get("p", String.class).orElse(null)
        );
        assertEquals(
            "string-value",
            root.get("dict-key.p", String.class).orElse(null)
        );

        config = root.get("list-key", Configuration.class).orElse(null);
        assertNotNull(config);
        assertEquals(root, config.getParent().orElse(null));
        assertEquals(
            "some-str",
            config.get("0", String.class).orElse(null)
        );
        assertEquals(
            "some-str",
            config.getChild(0, String.class).orElse(null)
        );
        assertEquals(
            "some-str",
            root.get("list-key.0", String.class).orElse(null)
        );

        config = root.get("list-key.1", Configuration.class).orElse(null);
        assertNotNull(config);
        assertEquals(
            root,
            config.getParent().orElse(null).getParent().orElse(null)
        );
        assertTrue(config.get("x", Configuration.class).isPresent());
    }

    @Test
    public void testSetConfiguration() {
        Configuration root;
        Supplier<Configuration> makeRoot = () ->
            (Configuration) Configuration.parseValue(
                ImmutableMap.of(
                    "int-key", 1,
                    "dict-key", ImmutableMap.of(
                        "p", "string-value"
                    ),
                    "list-key", ImmutableList.of(
                        "some-str",
                        ImmutableMap.of(
                            "x", ImmutableMap.of()
                        )
                    )
                )
            );

        root = makeRoot.get();

        assertEquals(
            Integer.valueOf(1),
            root.get("int-key", Integer.class).orElse(null)
        );
        root.set("int-key", 2);
        assertEquals(
            Integer.valueOf(2),
            root.get("int-key", Integer.class).orElse(null)
        );

        assertFalse(root.get("x", Object.class).isPresent());
        root.set("x", 99);
        assertEquals(
            Integer.valueOf(99),
            root.get("x", Integer.class).orElse(null)
        );

        assertEquals(
            "some-str",
            root.get("list-key.0", String.class).orElse(null)
        );
        root.set("list-key.0", 99);
        assertEquals(
            Integer.valueOf(99),
            root.get("list-key.0", Integer.class).orElse(null)
        );

        root.set("list-key.1.x.y", 99);
        assertEquals(
            Integer.valueOf(99),
            root.get("list-key.1.x.y", Integer.class).orElse(null)
        );

        assertTrue(root.get("list-key.1", Object.class).isPresent());
        root.remove("list-key.1");
        assertFalse(root.get("list-key.1", Object.class).isPresent());
    }

    @Test
    public void testConfigOverwrites() throws IOException {
        Configuration.Args args = new Configuration.Args();
        Configuration config;
        ImmutableMap<String, Object> expect;
        Throwable exc;

        args.configOverwrites = ImmutableMap.of();
        config = Configuration.parse(args);
        assertFalse(config.getParent().isPresent());
        assertEquals(0L, config.children().count());

        args.configOverwrites = ImmutableMap.of(
            "x", "1",
            "y", "hello",
            "z", "true"
        );
        expect = ImmutableMap.of(
            "x", 1,
            "y", "hello",
            "z", Boolean.TRUE
        );
        config = Configuration.parse(args);
        assertFalse(config.getParent().isPresent());
        assertEquals(expect.size(), config.children().count());
        for (String key : expect.keySet()) {
            Object value = expect.get(key);
            assertEquals(
                value,
                config.get(key, value.getClass()).orElse(null)
            );
        }

        args.configOverwrites = ImmutableMap.of(
            "x", "{}"
        );
        exc = assertThrows(
            IllegalArgumentException.class,
            () -> Configuration.parse(args)
        );
        assertEquals("Not primitive overwrite value: {}", exc.getMessage());

        args.configOverwrites = ImmutableMap.of(
            "x", "[]"
        );
        exc = assertThrows(
            IllegalArgumentException.class,
            () -> Configuration.parse(args)
        );
        assertEquals("Not primitive overwrite value: []", exc.getMessage());
    }

    @Test
    public void testNonStringPath() {
        Throwable exc = assertThrows(
            IllegalArgumentException.class,
            () -> Configuration.parseValue(ImmutableMap.of(1, 1))
        );
        assertTrue(exc.getMessage().matches("Invalid key type: .*"));
    }
}
