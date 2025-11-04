pub mod download;
pub mod push;
pub mod upload;

//
// NOTE: TODO: I have a feeling this might come back to bite us.  We are trying to register
// callbacks for the torrent and peer lifetimes (`bt_model::ModelUpdate`).  The problem is that
// these callbacks are not synchronous, which means that by the time they are called, the torrent
// or peer may have been reinitialized or reconnected.  I do not know how to fix this issue -
// making these callbacks synchronous does not feel like the right solution.
//
