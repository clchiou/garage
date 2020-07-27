package g1.base;

import com.google.common.collect.ImmutableList;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Tag("fast")
public class ConfigurationLoaderTest {

    private ConfigurationLoader loader;

    @BeforeEach
    public void setUp() {
        loader = new ConfigurationLoader(ImmutableList.of("g1.base"));
    }

    @AfterEach
    public void tearDown() {
        Data.reset();
    }

    private Path createTempPath(String content) throws IOException {
        Path path = Files.createTempFile(null, null);
        path.toFile().deleteOnExit();
        Files.write(path, content.getBytes(StandardCharsets.UTF_8));
        return path;
    }

    @Test
    public void testEmpty() throws IOException {
        loader.loadFromFiles(ImmutableList.of(createTempPath("")));
        Data.assertInitialState();
    }

    @Test
    public void testNonMap() throws IOException {
        loader.loadFromFiles(ImmutableList.of(createTempPath("[]")));
        Data.assertInitialState();
    }

    @Test
    public void testNonStringKey() throws IOException {
        loader.loadFromFiles(ImmutableList.of(createTempPath("1: {i: 1}")));
        Data.assertInitialState();
    }

    @Test
    public void testNonMapValue() throws IOException {
        loader.loadFromFiles(
            ImmutableList.of(createTempPath("g1.base.Data: 1")));
        Data.assertInitialState();
    }

    @Test
    public void testWrongValueType() throws IOException {
        loader.loadFromFiles(
            ImmutableList.of(createTempPath("g1.base.Data: {s: 1}")));
        Data.assertInitialState();
    }

    @Test
    public void testUnknownClass() throws IOException {
        loader.loadFromFiles(
            ImmutableList.of(createTempPath("no.such.Class: {i: 1}")));
        Data.assertInitialState();
    }

    @Test
    public void testUnknownField() throws IOException {
        loader.loadFromFiles(
            ImmutableList.of(createTempPath("g1.base.Data: {x: 1}")));
        Data.assertInitialState();
    }

    @Test
    public void testLoad() throws IOException {
        String content = String.join(
            "\n",
            "g1.base.Data:",
            "  i: 1",
            "  integer: 2",
            "  s: hello world",
            "g1.base.Data.Nested:",
            "  i: 11",
            "  integer: 22",
            "  s: spam egg"
        );
        loader.loadFromFiles(ImmutableList.of(createTempPath(content)));
        assertEquals(1, Data.i);
        assertEquals(2, Data.integer);
        assertEquals("hello world", Data.s);
        assertEquals(11, Data.Nested.i);
        assertEquals(22, Data.Nested.integer);
        assertEquals("spam egg", Data.Nested.s);
        Data.assertSkippedFields();
    }

    @Test
    public void testOverwrite() throws IOException {
        loader.loadFromFiles(
            ImmutableList.of(
                createTempPath("g1.base.Data: {i: 1}"),
                createTempPath("g1.base.Data: {i: 2}")
            )
        );
        assertEquals(2, Data.i);
    }
}
