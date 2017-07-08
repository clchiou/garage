package nanomsg;

import com.google.common.base.Preconditions;

import nanomsg.Nanomsg.nn_symbol_properties;

import static nanomsg.Nanomsg.symbol;

public enum Protocol {

    NN_PAIR(symbol("NN_PAIR")),
    NN_PUB(symbol("NN_PUB")),
    NN_SUB(symbol("NN_SUB")),
    NN_REP(symbol("NN_REP")),
    NN_REQ(symbol("NN_REQ")),
    NN_PUSH(symbol("NN_PUSH")),
    NN_PULL(symbol("NN_PULL")),
    NN_SURVEYOR(symbol("NN_SURVEYOR")),
    NN_RESPONDENT(symbol("NN_RESPONDENT")),
    NN_BUS(symbol("NN_BUS"));

    final int value;

    Protocol(nn_symbol_properties props) {
        Preconditions.checkArgument(
            props.ns == Namespace.NN_NS_PROTOCOL.value);
        value = props.value;
    }
}
