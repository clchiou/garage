package g1.base;

import static org.junit.jupiter.api.Assertions.assertEquals;

public class Data {

    @Configuration
    public static int i = 0;
    @Configuration
    public static Integer integer = 0;
    @Configuration
    public static String s = "";

    @Configuration
    public final static int skippedFinal = 0;
    @Configuration
    protected static int skippedProtected = 0;
    @Configuration
    static int skippedPackagePrivate = 0;
    @Configuration
    private static int skippedPrivate = 0;

    @Configuration
    public int skippedNonStatic = 0;

    public static void reset() {
        i = 0;
        integer = 0;
        s = "";
        Nested.reset();
    }

    public static void assertSkippedFields() {
        assertEquals(0, skippedFinal);
        assertEquals(0, skippedPackagePrivate);
        assertEquals(0, skippedProtected);
        assertEquals(0, skippedPrivate);
    }

    public static void assertInitialState() {
        assertEquals(0, i);
        assertEquals(0, integer);
        assertEquals("", s);
        assertSkippedFields();
        Nested.assertInitialState();
    }

    public static class Nested {
        @Configuration
        public static int i = 0;
        @Configuration
        public static Integer integer = 0;
        @Configuration
        public static String s = "";

        @Configuration
        public final static int skippedFinal = 0;
        @Configuration
        protected static int skippedProtected = 0;
        @Configuration
        static int skippedPackagePrivate = 0;
        @Configuration
        private static int skippedPrivate = 0;

        @Configuration
        public int skippedNonStatic = 0;

        public static void reset() {
            i = 0;
            integer = 0;
            s = "";
        }

        public static void assertSkippedFields() {
            assertEquals(0, skippedFinal);
            assertEquals(0, skippedPackagePrivate);
            assertEquals(0, skippedProtected);
            assertEquals(0, skippedPrivate);
        }

        public static void assertInitialState() {
            assertEquals(0, i);
            assertEquals(0, integer);
            assertEquals("", s);
            assertSkippedFields();
        }
    }
}
