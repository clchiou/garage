package nanomsg;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import nanomsg.Nanomsg.nn_symbol_properties;

import static org.junit.jupiter.api.Assertions.*;

@Tag("fast")
public class NanomsgTest {

    @Test
    public void testSymbol() {

        int numNamespaces = 0;
        int numTypes = 0;
        int numUnits = 0;
        int numSymbols = 0;
        for (nn_symbol_properties props : Nanomsg.SYMBOLS.values()) {
            if (props.ns == Symbol.Namespace.NN_NS_NAMESPACE.value) {
                numNamespaces++;
            } else if (props.ns == Symbol.Namespace.NN_NS_OPTION_TYPE.value) {
                numTypes++;
            } else if (props.ns == Symbol.Namespace.NN_NS_OPTION_UNIT.value) {
                numUnits++;
            } else {
                numSymbols++;
            }
        }

        // Ensure that we enumerate all symbols.
        assertEquals(numNamespaces, Symbol.Namespace.values().length);
        assertEquals(numTypes, Symbol.Type.values().length);
        assertEquals(numUnits, Symbol.Unit.values().length);
        assertEquals(numSymbols, Symbol.values().length);

        // Ensure that there is no typo in symbol name.
        for (Symbol symbol : Symbol.values()) {
            assertEquals(symbol.name, symbol.name());
        }
    }

    @Test
    public void testError() {

        assertEquals(new Error(0), new Error(0));
        assertEquals(new Error(0).hashCode(), new Error(0).hashCode());

        assertNotEquals(new Error(0), new Error(1));
        assertNotEquals(new Error(0).hashCode(), new Error(1).hashCode());
    }
}
