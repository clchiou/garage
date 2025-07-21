mod target;

use std::collections::{BTreeMap, HashSet};

use g1_base::collections::Array;

use bt_base::NodeId;
use bt_base::node_id::NodeDistance;
use bt_dht_proto::{Message, NodeInfo, Response};

use crate::target::Acc;

//
// Example usage of `Lookup`:
// ```
// let mut bootstrap = routing_table.get_closest(...);
// if bootstrap.is_empty() {
//     bootstrap = <bootstrap>;
// }
//
// let mut lookup = Lookup::new(..., bootstrap);
//
// while let Some(queries) = lookup.next() {
//     for (info, query) in queries {
//         let response = <send_query>;
//
//         if let Err(response) = lookup.update(info, response) {
//             <handle_error>;
//         }
//
//         <insert_routing_table>;
//     }
// }
//
// lookup.finish()
// ```
//

pub const ALPHA: usize = 3;

pub use crate::target::{LookupPeers, Target};

#[derive(Debug)]
pub struct Lookup<T>
where
    T: Target,
{
    self_id: NodeId,

    target: T,

    // Sorted by their distance to `target`.  There will be no duplicate entries, since `XOR`
    // ensures that `p == q` if and only if `d(p, target) == d(q, target)`.
    queue: BTreeMap<NodeDistance, NodeInfo>,

    // Closest nodes used to test convergence.
    closest: Array<NodeId, ALPHA>,

    // If a node has multiple endpoints, we decide to query only one of them, even if the query
    // fails.
    queried: HashSet<NodeId>,

    acc: T::Acc,
}

impl<T> Lookup<T>
where
    T: Target,
{
    pub fn new<I>(self_id: NodeId, target: T, bootstrap: I) -> Self
    where
        I: IntoIterator<Item = NodeInfo>,
    {
        let mut queue = BTreeMap::new();
        extend_queue(&mut queue, &target, bootstrap);
        assert!(!queue.is_empty());
        Self {
            self_id,
            target,
            queue,
            closest: Array::new(),
            queried: HashSet::new(),
            acc: T::Acc::new(),
        }
    }

    // NOTE: It also checks for convergence, meaning that if you call it repeatedly without calling
    // `update`, it will incorrectly conclude that the lookup has converged and return `None`.
    pub fn next_iteration(&mut self) -> Option<Array<(NodeInfo, Message), ALPHA>> {
        let closest = self
            .queue
            .values()
            .map(|info| info.id.clone())
            .take(ALPHA)
            .collect();
        if closest == self.closest {
            return None; // Lookup has converged.
        }
        self.closest = closest;

        let mut queries = Array::new();
        for info in self.queue.values() {
            if self.queried.contains(&info.id) {
                continue;
            }

            // We update `queried` before actually sending the query to the node, based on the
            // decision not to query the same node again, even if the previous query failed.
            self.queried.insert(info.id.clone());

            queries.push((info.clone(), self.target.new_query(self.self_id.clone())));
            if queries.is_full() {
                break;
            }
        }
        (!queries.is_empty()).then_some(queries)
    }

    // TODO: Should we fix `result_large_err`?
    #[allow(clippy::result_large_err)]
    pub fn update(&mut self, info: NodeInfo, response: Response) -> Result<(), Response> {
        extend_queue(
            &mut self.queue,
            &self.target,
            self.acc.update(&self.target, info, response)?,
        );
        Ok(())
    }

    pub fn finish(self) -> T::Output {
        self.acc.finish()
    }
}

fn extend_queue<T, I>(queue: &mut BTreeMap<NodeDistance, NodeInfo>, target: &T, infos: I)
where
    T: Target,
    I: IntoIterator<Item = NodeInfo>,
{
    let t = target.to_id();
    for info in infos {
        queue.insert(info.id.distance(&t), info);
    }
}
