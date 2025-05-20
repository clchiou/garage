use std::future::Future;

use uuid::Uuid;

use g1_base::future::ReadyQueue;

use crate::error::Error;
use crate::{RawClient, ResponseResult};

#[tracing::instrument(skip_all)]
pub async fn request<Requester, Fut>(
    servers: impl IntoIterator<Item = (Uuid, RawClient)>,
    mut requester: Requester,
    first: bool,
) -> ResponseResult
where
    Requester: FnMut(RawClient) -> Fut,
    Fut: Future<Output = ResponseResult> + Send + 'static,
{
    let request_queue = ReadyQueue::new();
    for (id, client) in servers.into_iter() {
        let response = requester(client.clone());
        assert!(
            request_queue
                .push(async move { (id, response.await) })
                .is_ok()
        );
    }
    request_queue.close();

    let mut result = None;
    let mut err_acc = None;
    while let Some((id, response)) = request_queue.pop_ready().await {
        match response {
            Ok(new_result @ Some(_)) => {
                result = new_result;
                if first {
                    break;
                }
            }
            Ok(None) => {}
            Err(error) => err_acc = fold_err(err_acc, id, error),
        }
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

fn fold_err(mut err_acc: Option<(Uuid, Error)>, id: Uuid, error: Error) -> Option<(Uuid, Error)> {
    if let Some((id, error)) = err_acc.replace((id, error)) {
        tracing::warn!(%id, %error);
    }
    err_acc
}
