package nanomsg;

import com.google.common.base.Preconditions;

import nanomsg.Nanomsg.nn_symbol_properties;

import static nanomsg.Nanomsg.symbol;

public enum Domain {

    AF_SP(symbol("AF_SP")),
    AF_SP_RAW(symbol("AF_SP_RAW"));

    final int value;

    Domain(nn_symbol_properties props) {
        Preconditions.checkArgument(props.ns == Namespace.NN_NS_DOMAIN.value);
        value = props.value;
    }
}
