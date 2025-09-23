use std::fmt::Debug;
use std::time::Duration;

use snafu::prelude::*;
use tokio::time;
use tokio::time::error::Elapsed;

use g1_tokio::sync::broadcast::{self, Receiver, Sender};

use crate::error::{BroadcastSnafu, ConnActorError, Error};

// I am not sure if this is a good idea, but let us try using `broadcast` (instead of the usual
// `mpsc`) in this case.
#[derive(Clone, Debug)]
pub(crate) struct Broadcast<T>(Sender<T>);

// TODO: Make this configurable.
const SEND_TIMEOUT: Duration = Duration::from_secs(2);

impl<T> Broadcast<T>
where
    T: Clone,
{
    pub(crate) fn new() -> Self {
        // TODO: Make channel capacity configurable.
        Self(broadcast::channel(64).0)
    }
}

impl<T> Broadcast<T>
where
    T: Debug,
{
    pub(crate) async fn send(&self, message: T) -> Result<(), Error> {
        match time::timeout(SEND_TIMEOUT, self.0.send(message)).await {
            Ok(result) => {
                if let Err(broadcast::error::SendError(message)) = result {
                    tracing::warn!(?message, "no receiver; drop");
                }
                Ok(())
            }
            Err(Elapsed { .. }) => Err(Error),
        }
    }

    pub(crate) async fn actor_send(&self, message: T) -> Result<(), ConnActorError> {
        self.send(message).await.context(BroadcastSnafu)
    }

    pub(crate) fn subscribe(&self) -> Receiver<T> {
        self.0.subscribe()
    }
}
