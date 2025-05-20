use std::collections::HashMap;
use std::collections::hash_map::Entry;
use std::error;
use std::fmt;

use serde_yaml::Value;

//
// TODO: Should we provide both owning and borrowing versions of `Tree`?
//
// TODO: Should we also recurse into `Value::Sequence`?  But then how would `merge_from` merge two
// sequences --- by appending them?
//
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Tree {
    Subtree(HashMap<String, Tree>),
    Leaf(Value),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct TryFromValueError;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct MergeError;

impl TryFrom<Value> for Tree {
    type Error = TryFromValueError;

    fn try_from(value: Value) -> Result<Self, Self::Error> {
        fn try_into_string(value: Value) -> Result<String, TryFromValueError> {
            match value {
                Value::String(string) => Ok(string),
                _ => Err(TryFromValueError),
            }
        }

        Ok(match value {
            Value::Mapping(map) => Self::Subtree(
                map.into_iter()
                    .map(|(key, value)| Ok((try_into_string(key)?, value.try_into()?)))
                    .try_collect()?,
            ),
            _ => Self::Leaf(value),
        })
    }
}

impl From<Tree> for Value {
    fn from(tree: Tree) -> Self {
        match tree {
            Tree::Subtree(map) => Self::Mapping(
                map.into_iter()
                    .map(|(key, subtree)| (key.into(), subtree.into()))
                    .collect(),
            ),
            Tree::Leaf(value) => value,
        }
    }
}

impl Default for Tree {
    fn default() -> Self {
        Self::new()
    }
}

impl Tree {
    pub fn new() -> Self {
        Self::Subtree(HashMap::new())
    }

    pub fn as_subtree(&self) -> Option<&HashMap<String, Tree>> {
        match self {
            Self::Subtree(map) => Some(map),
            Self::Leaf(_) => None,
        }
    }

    pub fn as_subtree_mut(&mut self) -> Option<&mut HashMap<String, Tree>> {
        match self {
            Self::Subtree(map) => Some(map),
            Self::Leaf(_) => None,
        }
    }

    pub fn as_leaf(&self) -> Option<&Value> {
        match self {
            Self::Subtree(_) => None,
            Self::Leaf(value) => Some(value),
        }
    }

    pub fn as_leaf_mut(&mut self) -> Option<&mut Value> {
        match self {
            Self::Subtree(_) => None,
            Self::Leaf(value) => Some(value),
        }
    }

    /// Merges the other tree into `self` recursively.
    ///
    /// The trees must have the same "shape", and the entries from the other tree take precedence
    /// during the merge.
    pub fn merge_from(&mut self, other: Tree) -> Result<&mut Self, MergeError> {
        match (&mut *self, other) {
            (Self::Subtree(this), Self::Subtree(that)) => {
                for (key, subtree) in that {
                    let _ = match this.entry(key) {
                        Entry::Occupied(entry) => entry.into_mut().merge_from(subtree)?,
                        Entry::Vacant(entry) => entry.insert(subtree),
                    };
                }
            }
            (Self::Leaf(this), Self::Leaf(that)) => *this = that,
            _ => return Err(MergeError),
        }
        // TODO: Should we change the return type to `Result<(), ...>` instead?
        Ok(self)
    }
}

impl fmt::Display for TryFromValueError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("TryFromValueError")
    }
}

impl error::Error for TryFromValueError {}

impl fmt::Display for MergeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("MergeError")
    }
}

impl error::Error for MergeError {}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(yaml: &str) -> Value {
        serde_yaml::from_str(yaml).unwrap()
    }

    fn t<const N: usize>(entries: [(&str, Tree); N]) -> Tree {
        Tree::Subtree(
            entries
                .into_iter()
                .map(|(key, subtree)| (key.into(), subtree))
                .collect(),
        )
    }

    fn l(value: Value) -> Tree {
        Tree::Leaf(value)
    }

    #[test]
    fn try_from() {
        assert_eq!(Tree::try_from(v("42")), Ok(l(v("42"))));

        assert_eq!(Tree::try_from(v("{}")), Ok(t([])));

        assert_eq!(
            Tree::try_from(v("{w: {}, x: 'spam', y: {z: 'egg'}}")),
            Ok(t([
                ("w", t([])),
                ("x", l(v("'spam'"))),
                ("y", t([("z", l(v("'egg'")))])),
            ])),
        );

        assert_eq!(Tree::try_from(v("{1: x}")), Err(TryFromValueError));
    }

    #[test]
    fn from() {
        for testdata in ["42", "{}", "{v: 1, w: {x: 2, y: {z: 3}}}"] {
            let testdata = v(testdata);
            let tree = Tree::try_from(testdata.clone()).unwrap();
            assert_eq!(Value::from(tree), testdata);
        }
    }

    #[test]
    fn merge_from() {
        {
            let mut expect = l(v("1"));

            let this = v("0");
            let mut this = Tree::try_from(this).unwrap();

            let that = v("1");
            let that = Tree::try_from(that).unwrap();

            assert_eq!(this.merge_from(that), Ok(&mut expect));
            assert_eq!(this, expect);
        }

        {
            let mut expect = t([
                ("s", l(v("3"))),
                ("t", t([("u", l(v("4")))])),
                ("v", l(v("0"))),
                ("w", l(v("5"))),
                ("x", t([("y", t([("z", l(v("6")))]))])),
            ]);

            let this = v("{                 v: 0, w: 1, x: {y: {z: 2}}}");
            let mut this = Tree::try_from(this).unwrap();

            let that = v("{s: 3, t: {u: 4},       w: 5, x: {y: {z: 6}}}");
            let that = Tree::try_from(that).unwrap();

            assert_eq!(this.merge_from(that), Ok(&mut expect));
            assert_eq!(this, expect);
        }

        for (this, that) in [
            ("0", "{}"),
            ("{}", "0"),
            ("{x: 0}", "{x: {}}"),
            ("{x: {}}", "{x: 0}"),
        ] {
            let this = v(this);
            let mut this = Tree::try_from(this).unwrap();
            let that = v(that);
            let that = Tree::try_from(that).unwrap();
            assert_eq!(this.merge_from(that), Err(MergeError));
        }
    }
}
