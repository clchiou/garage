mod loop_;
mod message;
mod parse;
mod stub;

use proc_macro2::TokenStream;
use syn::punctuated::Punctuated;
use syn::visit_mut::VisitMut;
use syn::{
    Error, Expr, Field, Generics, Ident, ItemImpl, Pat, Path, PathArguments, PathSegment, Token,
    Type, TypePath, Visibility,
};

use crate::replace;

pub(crate) fn actor(mut args: ActorArgs, mut input: ItemImpl) -> Result<TokenStream, Error> {
    let actor = Actor::parse(&input)?;
    args.parse_from(&input)?;

    Actor::clear_annotations(&mut input);
    ActorArgs::clear_annotations(&mut input);

    let codegen = Codegen::new(args, actor);
    let stub = codegen.generate_stub();
    let message = codegen.generate_message();
    let loop_ = codegen.generate_loop();
    Ok(quote::quote! {
        #input
        #stub
        #message
        #loop_
    })
}

#[cfg_attr(test, derive(Clone, Debug, Default, PartialEq))]
pub(crate) struct ActorArgs {
    stub: Stub,
    message: Message,
    loop_: Loop,
}

struct Codegen {
    stub: Stub,
    stub_type_name: Ident,
    stub_derive: Vec<Ident>,

    message: Message,
    message_type_name: Ident,
    message_queue_name: Ident,

    loop_: Loop,
    loop_type_name: Ident,

    spawn_func_name: Ident,
    new_func_name: Ident,
    run_func_name: Ident,

    actor: Actor,
    actor_type_name: Path,
    actor_type_simple_name: Path,
    actor_name: Ident,
}

#[derive(Default)]
#[cfg_attr(test, derive(Clone, Debug, PartialEq))]
struct Stub {
    skip: bool,

    visibility: Option<Visibility>,

    name: Option<Ident>,
    derive: Option<Vec<Ident>>,

    fields: Fields,

    spawn: AssocFunc,
    new: AssocFunc,
}

type Fields = Punctuated<Field, Token![,]>;

#[derive(Default)]
#[cfg_attr(test, derive(Clone, Debug, PartialEq))]
struct Message {
    skip: bool,

    visibility: Option<Visibility>,

    name: Option<Ident>,
}

#[derive(Default)]
#[cfg_attr(test, derive(Clone, Debug, PartialEq))]
struct Loop {
    skip: bool,

    visibility: Option<Visibility>,

    name: Option<Ident>,

    new: AssocFunc,
    // This is intended for the user to rename `run` and create their own.
    run: AssocFunc,

    reacts: Vec<(Pat, Expr, Expr)>,

    ret_type: Option<Type>,
    ret_value: Option<Expr>,
}

#[derive(Default)]
#[cfg_attr(test, derive(Clone, Debug, PartialEq))]
struct AssocFunc {
    skip: bool,

    visibility: Option<Visibility>,

    name: Option<Ident>,
}

#[cfg_attr(test, derive(Clone, Debug, PartialEq))]
struct Actor {
    // TODO: Support types like `Arc<Mutex<Actor>>`.
    type_: Type,

    generics: Generics,
    // For lack of a better term, we split `input.generics` into two groups: "exposed" and
    // "not exposed".  The "exposed" group consists of generic parameters and their predicates that
    // are exposed by an actor method.  This group is used in stub and message code generation,
    // whereas the "not exposed" group is used in loop code generation.
    exposed: Generics,
    not_exposed: Generics,

    methods: Vec<Method>,
}

#[cfg_attr(test, derive(Clone, Debug, PartialEq))]
struct Method {
    // From attribute, not from the method declaration.
    visibility: Option<Visibility>,

    asyncness: bool,

    name: Ident,

    has_receiver: bool,

    arg_types: Vec<Type>,
    arg_names: Vec<Ident>,

    ret_type: Type,
    // From attribute.
    ret_expr: Option<(Ident, Expr)>,
}

impl Codegen {
    fn new(args: ActorArgs, actor: Actor) -> Self {
        let ActorArgs {
            stub,
            message,
            loop_,
        } = args;

        let base_name = actor.base_name();
        let make_name = |arg: &Option<_>, suffix| {
            arg.clone()
                .unwrap_or_else(|| quote::format_ident!("{base_name}{suffix}"))
        };
        let stub_type_name = make_name(&stub.name, "Stub");
        let message_type_name = make_name(&message.name, "Message");
        let loop_type_name = make_name(&loop_.name, "Loop");

        let actor_type_name = actor.to_turbofish();
        let actor_type_simple_name = actor.to_simple_path();

        Self {
            stub,
            stub_type_name,
            stub_derive: vec![quote::format_ident!("Clone"), quote::format_ident!("Debug")],

            message,
            message_type_name,
            message_queue_name: quote::format_ident!("__message_queue"),

            loop_,
            loop_type_name,

            spawn_func_name: quote::format_ident!("spawn"),
            new_func_name: quote::format_ident!("new"),
            run_func_name: quote::format_ident!("run"),

            actor,
            actor_type_name,
            actor_type_simple_name,
            actor_name: quote::format_ident!("__actor"),
        }
    }

    /// True if `struct Stub` is a zero-sized type.
    fn is_stub_zero_sized(&self) -> bool {
        self.actor.methods.is_empty() && self.stub.fields.is_empty()
    }

    /// True if `enum Message` is an empty type.
    fn is_message_empty(&self) -> bool {
        self.actor.methods.is_empty()
    }

    /// True if `Loop::run` is trivial.
    fn is_loop_trivial(&self) -> bool {
        self.actor.methods.is_empty() && self.loop_.reacts.is_empty()
    }

    fn expr_replace_self_keyword(&self, expr: &mut Expr) {
        replace::simple_path_replacer("Self", || self.actor_type_name.clone()).visit_expr_mut(expr);
        replace::ident_replacer("self", || self.actor_name.clone()).visit_expr_mut(expr);
    }

    fn pat_replace_self_keyword(&self, pat: &mut Pat) {
        replace::simple_path_replacer("Self", || self.actor_type_simple_name.clone())
            .visit_pat_mut(pat);
    }
}

impl Actor {
    // NOTE: `Actor::parse` has verified that `type_` matches the shape of `module::Actor<T>`.
    fn path(&self) -> &Path {
        match &self.type_ {
            Type::Path(TypePath { qself: None, path }) => path,
            _ => unreachable!(),
        }
    }

    fn base_name(&self) -> &Ident {
        let path = self.path();
        &path.segments[path.segments.len() - 1].ident
    }

    fn to_turbofish(&self) -> Path {
        Path {
            leading_colon: self.path().leading_colon,
            segments: self.make_turbofishes().collect(),
        }
    }

    fn to_simple_path(&self) -> Path {
        Path {
            leading_colon: self.path().leading_colon,
            segments: self.make_simple_segments().collect(),
        }
    }

    fn make_turbofishes(&self) -> impl Iterator<Item = PathSegment> {
        self.path().segments.iter().cloned().map(|mut segment| {
            if let PathArguments::AngleBracketed(angle) = &mut segment.arguments {
                angle.colon2_token = Some(Default::default());
            }
            segment
        })
    }

    fn make_simple_segments(&self) -> impl Iterator<Item = PathSegment> {
        self.path().segments.iter().map(|segment| PathSegment {
            ident: segment.ident.clone(),
            arguments: PathArguments::None,
        })
    }
}

impl Method {
    fn arg_pairs(&self) -> impl Iterator<Item = (&Ident, &Type)> {
        self.arg_names.iter().zip(&self.arg_types)
    }
}

const INHERITED: Visibility = Visibility::Inherited;

impl Stub {
    fn visibility(&self) -> &Visibility {
        self.visibility.as_ref().unwrap_or(&INHERITED)
    }
}

impl Message {
    fn visibility(&self) -> &Visibility {
        self.visibility.as_ref().unwrap_or(&INHERITED)
    }
}

impl Loop {
    fn visibility(&self) -> &Visibility {
        self.visibility.as_ref().unwrap_or(&INHERITED)
    }
}

impl AssocFunc {
    fn visibility(&self) -> &Visibility {
        self.visibility.as_ref().unwrap_or(&INHERITED)
    }
}

impl Method {
    fn visibility(&self) -> &Visibility {
        self.visibility.as_ref().unwrap_or(&INHERITED)
    }
}

#[cfg(test)]
mod testing {
    use proc_macro2::TokenStream;
    use syn::ItemImpl;

    use super::{Actor, Codegen};

    impl Codegen {
        pub(crate) fn new_mock(args: TokenStream, input: &ItemImpl) -> Self {
            Self::new(syn::parse2(args).unwrap(), Actor::parse(&input).unwrap())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codegen() {
        fn test(
            args: TokenStream,
            input: &ItemImpl,
            expect_stub_zero_sized: bool,
            expect_message_empty: bool,
            expect_loop_trivial: bool,
        ) {
            let codegen = Codegen::new_mock(args, input);
            assert_eq!(codegen.is_stub_zero_sized(), expect_stub_zero_sized);
            assert_eq!(codegen.is_message_empty(), expect_message_empty);
            assert_eq!(codegen.is_loop_trivial(), expect_loop_trivial);
        }

        let input = syn::parse_quote! { impl Foo {} };
        test(quote::quote!(), &input, true, true, true);
        test(
            quote::quote!(stub(struct { x: u8 })),
            &input,
            false,
            true,
            true,
        );
        test(
            quote::quote!(loop_(
                react = {
                    let x = x;
                }
            )),
            &input,
            true,
            true,
            false,
        );

        let input = syn::parse_quote! {
            impl Foo {
                #[method()]
                fn f() {}
            }
        };
        test(quote::quote!(), &input, false, false, false);
        test(
            quote::quote!(stub(struct { x: u8 })),
            &input,
            false,
            false,
            false,
        );
        test(
            quote::quote!(loop_(
                react = {
                    let x = x;
                }
            )),
            &input,
            false,
            false,
            false,
        );
    }
}
