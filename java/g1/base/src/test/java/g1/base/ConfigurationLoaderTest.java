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
        loader.load(ImmutableList.of(createTempPath("")));
        Data.assertInitialState();
    }

    @Test
    public void testNonMap() throws IOException {
        loader.load(ImmutableList.of(createTempPath("[]")));
        Data.assertInitialState();
    }

    @Test
    public void testNonStringKey() throws IOException {
        loader.load(ImmutableList.of(createTempPath("1: {i: 1}")));
        Data.assertInitialState();
    }

    @Test
    public void testNonMapValue() throws IOException {
        loader.load(ImmutableList.of(createTempPath("g1.base.Data: 1")));
        Data.assertInitialState();
    }

    @Test
    public void testWrongValueType() throws IOException {
        loader.load(ImmutableList.of(createTempPath("g1.base.Data: {s: 1}")));
        Data.assertInitialState();
    }

    @Test
    public void testUnknownClass() throws IOException {
        loader.load(ImmutableList.of(createTempPath("no.such.Class: {i: 1}")));
        Data.assertInitialState();
    }

    @Test
    public void testUnknownField() throws IOException {
        loader.load(ImmutableList.of(createTempPath("g1.base.Data: {x: 1}")));
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
        loader.load(ImmutableList.of(createTempPath(content)));
        assertEquals(Data.i, 1);
        assertEquals(Data.integer, 2);
        assertEquals(Data.s, "hello world");
        assertEquals(Data.Nested.i, 11);
        assertEquals(Data.Nested.integer, 22);
        assertEquals(Data.Nested.s, "spam egg");
        Data.assertSkippedFields();
    }

    @Test
    public void testOverwrite() throws IOException {
        loader.load(
            ImmutableList.of(
                createTempPath("g1.base.Data: {i: 1}"),
                createTempPath("g1.base.Data: {i: 2}")
            )
        );
        assertEquals(Data.i, 2);
    }
}
