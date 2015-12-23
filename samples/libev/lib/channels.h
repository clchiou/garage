#ifndef CHANNELS_H_
#define CHANNELS_H_

enum {
	CHANNEL_RESERVED		= 0,

	// Session channels.
	CHANNEL_SESSION_INITIALIZED	= 1,
	CHANNEL_SESSION_DELETING	= 2,
	CHANNEL_SESSION_DELETED		= 3,
	CHANNEL_SESSION_DATA_RECEIVED	= 4,

	// User-defined channels start here.
	CHANNEL_USER			= 8,
};

#endif
