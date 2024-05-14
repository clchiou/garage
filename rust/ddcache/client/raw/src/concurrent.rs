use std::future::Future;

use tracing::Instrument;
use uuid::Uuid;

use g1_base::future::ReadyQueue;

use crate::error::Error;
use crate::response::{Response, ResponseResult};
use crate::RawClient;

#[tracing::instrument(skip_all)]
pub async fn request_any<Requester, Fut>(
    servers: impl IntoIterator<Item = (Uuid, RawClient)>,
    mut requester: Requester,
) -> Result<Option<(Uuid, RawClient, Response)>, Error>
where
    Requester: FnMut(RawClient) -> Fut,
    Fut: Future<Output = ResponseResult> + Send + 'static,
{
    let request_queue = ReadyQueue::new();
    for (id, client) in servers.into_iter() {
        let response = requester(client.clone());
        assert!(request_queue
            .push(async move { (id, client, response.await) })
            .is_ok());
    }
    request_queue.close();

    let mut result = None;
    let mut err_acc = None;
    while let Some((id, client, response)) = request_queue.pop_ready().await {
        match response {
            Ok(Some(response)) => {
                result = Some((id, client, response));
                break;
            }
            Ok(None) => {}
            Err(error) => err_acc = fold_err(err_acc, id, error),
        }
    }

    if !request_queue.is_empty() {
        tokio::spawn(
            cancel_rest(request_queue).instrument(tracing::info_span!("request_any/cancel")),
        );
    }

    if let Some((id, error)) = err_acc {
        if result.is_some() {
            tracing::warn!(%id, %error);
        } else {
            return Err(error);
        }
    }
    Ok(result)
}

async fn cancel_rest(request_queue: ReadyQueue<(Uuid, RawClient, ResponseResult)>) {
    let cancel_queue = ReadyQueue::new();
    loop {
        if request_queue.is_empty() {
            cancel_queue.close();
        }

        tokio::select! {
            Some((id, client, response)) = request_queue.pop_ready() => {
                match response {
                    Ok(Some(response)) => {
                        if let Some(blob) = response.blob.as_ref() {
                            let token = blob.token();
                            assert!(cancel_queue
                                .push(async move { (id, client.cancel(token).await) })
                                .is_ok());
                        }
                    }
                    Ok(None) => {}
                    Err(error) => tracing::warn!(%id, %error),
                }
            }

            Some((id, response)) = cancel_queue.pop_ready() => {
                if let Err(error) = response {
                    tracing::debug!(%id, %error);
                }
            }

            else => break,
        }
    }
}

#[tracing::instrument(skip_all)]
pub async fn request_all<Requester, FutR, F, Fut>(
    servers: impl IntoIterator<Item = (Uuid, RawClient)>,
    mut requester: Requester,
    mut f: F,
) -> Result<bool, Error>
where
    Requester: FnMut(RawClient) -> FutR,
    FutR: Future<Output = ResponseResult> + Send + 'static,
    F: FnMut(Response) -> Fut,
    Fut: Future<Output = Result<(), Error>> + Send + 'static,
{
    let request_queue = ReadyQueue::new();
    for (id, client) in servers.into_iter() {
        let response = requester(client);
        assert!(request_queue
            .push(async move { (id, response.await) })
            .is_ok());
    }
    request_queue.close();

    let mut succeed = false;
    let mut err_acc = None;
    let queue = ReadyQueue::new();
    loop {
        if request_queue.is_empty() {
            queue.close();
        }

        tokio::select! {
            Some((id, response)) = request_queue.pop_ready() => {
                match response {
                    Ok(Some(response)) => {
                        let future = f(response);
                        assert!(queue.push(async move { (id, future.await) }).is_ok());
                    }
                    Ok(None) => {}
                    Err(error) => tracing::warn!(%id, %error),
                }
            }

            Some((id, result)) = queue.pop_ready() => {
                match result {
                    Ok(()) => succeed = true,
                    Err(error) => err_acc = fold_err(err_acc, id, error),
                }
            }

            else => break,
        }
    }

    if let Some((id, error)) = err_acc {
        if succeed {
            tracing::warn!(%id, %error);
        } else {
            return Err(error);
        }
    }
    Ok(succeed)
}

fn fold_err(mut err_acc: Option<(Uuid, Error)>, id: Uuid, error: Error) -> Option<(Uuid, Error)> {
    if let Some((id, error)) = err_acc.replace((id, error)) {
        tracing::warn!(%id, %error);
    }
    err_acc
}
