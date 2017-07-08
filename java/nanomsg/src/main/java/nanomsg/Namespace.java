package nanomsg;

import com.google.common.base.Preconditions;

import nanomsg.Nanomsg.nn_symbol_properties;

import static nanomsg.Nanomsg.symbol;

public enum Namespace {

    NN_NS_NAMESPACE(symbol("NN_NS_NAMESPACE")),
    NN_NS_VERSION(symbol("NN_NS_VERSION")),
    NN_NS_DOMAIN(symbol("NN_NS_DOMAIN")),
    NN_NS_TRANSPORT(symbol("NN_NS_TRANSPORT")),
    NN_NS_PROTOCOL(symbol("NN_NS_PROTOCOL")),
    NN_NS_OPTION_LEVEL(symbol("NN_NS_OPTION_LEVEL")),
    NN_NS_SOCKET_OPTION(symbol("NN_NS_SOCKET_OPTION")),
    NN_NS_TRANSPORT_OPTION(symbol("NN_NS_TRANSPORT_OPTION")),
    NN_NS_OPTION_TYPE(symbol("NN_NS_OPTION_TYPE")),
    NN_NS_OPTION_UNIT(symbol("NN_NS_OPTION_UNIT")),
    NN_NS_FLAG(symbol("NN_NS_FLAG")),
    NN_NS_ERROR(symbol("NN_NS_ERROR")),
    NN_NS_LIMIT(symbol("NN_NS_LIMIT")),
    NN_NS_EVENT(symbol("NN_NS_EVENT")),
    NN_NS_STATISTIC(symbol("NN_NS_STATISTIC"));

    final int value;

    Namespace(nn_symbol_properties props) {
        Preconditions.checkArgument(props.ns == 0);
        value = props.value;
    }

    // This is only called during class load; so it is probably fine
    // that we do a linear search here.
    static Namespace byValue(int value) {
        for (Namespace namespace : values()) {
            if (namespace.value == value) {
                return namespace;
            }
        }
        throw new AssertionError();
    }
}
