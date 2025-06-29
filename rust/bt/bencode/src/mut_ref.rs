// Use `MutRef` to work around conflicting blanket implementations:
// ```
// impl<T> OurTrait for T where T: ExternalTrait { ... }
//
// // Conflict!
// impl<T> OurTrait for &mut T    where T: OurTrait { ... }
// // Ok.
// impl<T> OurTrait for MutRef<T> where T: OurTrait { ... }
// ```
pub(crate) struct MutRef<'a, T>(pub(crate) &'a mut T);
