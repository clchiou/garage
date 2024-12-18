#![allow(incomplete_features)]
#![feature(lazy_type_alias)]
#![feature(type_alias_impl_trait)]

use std::sync::Mutex;

use scopeguard::{Always, ScopeGuard};

use g1_base::fmt::{DebugExt, InsertPlaceholder};
use g1_base::sync::MutexExt;

#[derive(DebugExt)]
pub struct Pool<T, E> {
    #[debug(with = InsertPlaceholder)]
    pool: Mutex<Vec<T>>,
    size: usize,
    // We use `Box<dyn ...>` here because I think it is better not to expose an `F: Fn` to the
    // generic parameters of `Pool`.  We add `Send + Sync` because we need `Pool: Send + Sync`.
    #[debug(with = InsertPlaceholder)]
    make: Box<dyn Fn() -> Result<T, E> + Send + Sync>,
}

pub type Guard<'a, T, E>
    = ScopeGuard<T, impl FnOnce(T) + 'a, Always>
where
    T: 'a,
    E: 'a;

impl<T, E> Pool<T, E> {
    pub fn new<F>(size: usize, make: F) -> Self
    where
        F: Fn() -> Result<T, E> + Send + Sync + 'static,
    {
        Self {
            pool: Mutex::new(Vec::with_capacity(size)),
            size,
            make: Box::new(make),
        }
    }

    // This does not rate-limit (and blocks the caller); it simply creates a new `T` instance when
    // the pool is empty.  If this is an issue, the caller must implement rate limiting themselves.
    pub fn acquire(&self) -> Result<Guard<'_, T, E>, E> {
        let resource = match self.pool.must_lock().pop() {
            Some(resource) => resource,
            None => (self.make)()?,
        };
        Ok(scopeguard::guard(resource, |resource| {
            let mut pool = self.pool.must_lock();
            if pool.len() < self.size {
                pool.push(resource);
            }
        }))
    }
}
