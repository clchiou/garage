package g1.messaging;

import org.capnproto.MessageBuilder;
import org.capnproto.MessageReader;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.io.IOException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("fast")
public class WiredataTest {
    private static final MessageBuilder TEST_BUILDER;

    static {
        TEST_BUILDER = new MessageBuilder();
        Calculator.CalculatorRequest.Builder request = TEST_BUILDER.initRoot(
            Calculator.CalculatorRequest.factory
        );
        Calculator.CalculatorRequest.Args.Builder args = request.initArgs();
        Calculator.CalculatorRequest.Div.Builder div = args.initDiv();
        div.setX(1);
        div.setY(2);
    }

    @Test
    public void testUnpacked() throws IOException {
        testWiredata(Unpacked.WIREDATA);
    }

    @Test
    public void testPacked() throws IOException {
        testWiredata(Packed.WIREDATA);
    }

    private void testWiredata(Wiredata wiredata) throws IOException {
        MessageReader reader = wiredata.upper(wiredata.lower(TEST_BUILDER));
        Calculator.CalculatorRequest.Reader request = reader.getRoot(
            Calculator.CalculatorRequest.factory
        );
        Calculator.CalculatorRequest.Args.Reader args = request.getArgs();
        assertTrue(args.isDiv());
        Calculator.CalculatorRequest.Div.Reader div = args.getDiv();
        assertEquals(div.getX(), 1);
        assertEquals(div.getY(), 2);
    }
}
