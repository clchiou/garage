package nanomsg;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import nanomsg.Nanomsg.nn_symbol_properties;

import static org.junit.jupiter.api.Assertions.*;
import static nanomsg.Domain.AF_SP;
import static nanomsg.Protocol.*;
import static nanomsg.Option.*;

@Tag("fast")
public class NanomsgTest {

    @Test
    public void testSymbol() {

        int numNamespaces = 0;
        int numDomains = 0;
        int numProtocols = 0;
        int numOptions = 0;
        int numTypes = 0;
        int numUnits = 0;
        int numStatistics = 0;
        int numSymbols = 0;
        for (nn_symbol_properties props : Nanomsg.SYMBOLS.values()) {
            if (props.ns == Namespace.NN_NS_NAMESPACE.value) {
                numNamespaces++;
            } else if (props.ns == Namespace.NN_NS_DOMAIN.value) {
                numDomains++;
            } else if (props.ns == Namespace.NN_NS_PROTOCOL.value) {
                numProtocols++;
            } else if (props.ns == Namespace.NN_NS_SOCKET_OPTION.value) {
                numOptions++;
            } else if (props.ns == Namespace.NN_NS_TRANSPORT_OPTION.value) {
                numOptions++;
            } else if (props.ns == Namespace.NN_NS_OPTION_TYPE.value) {
                numTypes++;
            } else if (props.ns == Namespace.NN_NS_OPTION_UNIT.value) {
                numUnits++;
            } else if (props.ns == Namespace.NN_NS_STATISTIC.value) {
                numStatistics++;
            } else {
                numSymbols++;
            }
        }

        // Ensure that we enumerate all symbols.
        assertEquals(numNamespaces, Namespace.values().length);
        assertEquals(numDomains, Domain.values().length);
        assertEquals(numProtocols, Protocol.values().length);
        assertEquals(numOptions, Option.values().length);
        assertEquals(numTypes, Option.Type.values().length);
        assertEquals(numUnits, Option.Unit.values().length);
        assertEquals(numStatistics, Statistic.values().length);
        assertEquals(numSymbols, Symbol.values().length);
    }

    @Test
    public void testError() {

        assertEquals(new Error(0), new Error(0));
        assertEquals(new Error(0).hashCode(), new Error(0).hashCode());

        assertNotEquals(new Error(0), new Error(1));
        assertNotEquals(new Error(0).hashCode(), new Error(1).hashCode());
    }

    @Test
    public void testSocket() {
        try (Socket s1 = new Socket(AF_SP, NN_REQ);
             Socket s2 = new Socket(AF_SP, NN_REP)) {

            assertEquals(AF_SP.value, s1.getOption(NN_DOMAIN));
            assertEquals(NN_REQ.value, s1.getOption(NN_PROTOCOL));

            assertEquals(AF_SP.value, s2.getOption(NN_DOMAIN));
            assertEquals(NN_REP.value, s2.getOption(NN_PROTOCOL));

            s1.bind("inproc://testSocket");
            s2.connect("inproc://testSocket");

            byte[] req = new byte[]{0, 1, 2, 3, 4, 5};
            byte[] rep = new byte[req.length];

            s1.send(req, 0, req.length);
            assertEquals(req.length, s2.recv(rep, 0, rep.length));
            assertArrayEquals(req, rep);

            req = new byte[]{5, 4, 3, 2, 1, 0};
            s2.send(req, 0, req.length);
            assertEquals(req.length, s1.recv(rep, 0, rep.length));
            assertArrayEquals(req, rep);
        }
    }
}
