//
// I do not know if this is a good idea, but we add some control structures on top of `fragment`.
//

#[macro_export]
macro_rules! fragment_ext {
    ($w:expr => $($i:tt)*) => {
        $crate::_fx!([] [ $($i)* ] $w)
    };
}

#[macro_export]
macro_rules! _fx {
    ([ $($o:stmt;)* ] [] $w:expr) => { { $($o)* } };

    //
    // Top-level control structures.
    //

    ([ $($o:stmt;)* ] [ while ($p:expr) {                   $($q:tt)*     }      $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*          while  $p       { $crate::_fx!([] [ $($q)* ] $w); }; ] [ $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ] [ while let $n:pat = ($v:expr) {                   $($q:tt)*     }      $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*          while let $n     =  $v       { $crate::_fx!([] [ $($q)* ] $w); }; ] [ $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ] [ for $n:pat in ($v:expr) {                   $($q:tt)*     }      $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*          for $n     in  $v       { $crate::_fx!([] [ $($q)* ] $w); }; ] [ $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ] [ loop {                   $($q:tt)*     }      $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*          loop { $crate::_fx!([] [ $($q)* ] $w); }; ] [ $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ] [ match ($s:expr)            { $($ii:tt)* } $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*      ]   match  $s,      []         [ $($ii)*  ] [ $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ] [ if   (  $p:expr)            { $($q:tt)* }       $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*      ]   if [ (, $p, $crate::_fx!([] [ $($q)* ] $w)), ] [ $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ] [ if let $n:pat = ($v:expr)            { $($q:tt)* }        $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*      ]   if [  ($n,       $v, $crate::_fx!([] [ $($q)* ] $w)), ] [ $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ] [ break ;     $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*          break ; ] [ $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ] [ continue ;     $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*          continue ; ] [ $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ] [ return $($v:expr)? ;     $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*          return $($v)?      ; ] [ $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ] [ let $n:pat_param = ($v:expr) else $e:block ;     $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*          let $n           =  $v       else $e       ; ] [ $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ] [ let $n:pat_param = $v:expr ;     $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*          let $n           = $v      ; ] [ $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ] [ exec $e:block $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*               $e;  ] [ $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ] [   $f:tt  $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*      ] f [ $f ] [ $($i)*    ] $w     ) };

    //
    // `match` expression.
    //

    ([ $($o:stmt;)* ] match $s:expr, [ $(($a:pat, $($g:expr)?, $b:expr),)* ] [ $a1:pat $(if $g1:expr)? =>          { $($b1:tt)* }        $($ii:tt)* ] [ $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*      ] match $s     , [ $(($a    , $($g)?     , $b     ),)*    ($a1,       $($g1)?, $crate::_fx!([] [ $($b1)* ] $w)), ] [ $($ii)*    ] [ $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ] match $s:expr, [ $(($a:pat, $($g:expr)?, $b:expr),)* ] [] [ $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*        match $s       { $( $a   $(if $g)? =>  { $b }     )* }; ] [ $($i)*    ] $w) };

    //
    // `if` expression.
    //

    ([ $($o:stmt;)* ] if [ $(($($n:pat)?, $p:expr, $q:expr),)+ ] [ else if (  $p1:expr)            { $($q1:tt)* }        $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*      ] if [ $(($($n    )?, $p,      $q     ),)*             (, $p1, $crate::_fx!([] [ $($q1)* ] $w)), ] [ $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ] if [ $(($($n:pat)?, $p:expr, $q:expr),)+ ] [ else if let $n1:pat = (  $v1:expr)            { $($q1:tt)* }        $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*      ] if [ $(($($n    )?, $p,      $q     ),)*                ($n1,         $v1, $crate::_fx!([] [ $($q1)* ] $w)), ] [ $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ] if [ $(($($n:pat)?, $p:expr, $q:expr),)+ ] [ else {                     $($r:tt)* }         $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*      $(if  $(let $n   =)?  $p     { $q }            else)* { $crate::_fx!([] [ $($r)* ] $w) }; ] [ $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ] if [ $(($($n:pat)?, $p:expr, $q:expr),)+ ] [ $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*      $(if  $(let $n   =)?  $p     { $q })else*; ] [ $($i)*    ] $w     ) };

    //
    // Fragment.
    //

    ([ $($o:stmt;)* ]       f   [ $($f:tt)* ] [ while    $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)* $crate::_fx!(f $w, $($f)*);  ] [ while    $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ]       f   [ $($f:tt)* ] [ for      $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)* $crate::_fx!(f $w, $($f)*);  ] [ for      $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ]       f   [ $($f:tt)* ] [ loop     $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)* $crate::_fx!(f $w, $($f)*);  ] [ loop     $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ]       f   [ $($f:tt)* ] [ match    $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)* $crate::_fx!(f $w, $($f)*);  ] [ match    $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ]       f   [ $($f:tt)* ] [ if       $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)* $crate::_fx!(f $w, $($f)*);  ] [ if       $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ]       f   [ $($f:tt)* ] [ break    $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)* $crate::_fx!(f $w, $($f)*);  ] [ break    $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ]       f   [ $($f:tt)* ] [ continue $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)* $crate::_fx!(f $w, $($f)*);  ] [ continue $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ]       f   [ $($f:tt)* ] [ return   $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)* $crate::_fx!(f $w, $($f)*);  ] [ return   $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ]       f   [ $($f:tt)* ] [ let      $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)* $crate::_fx!(f $w, $($f)*);  ] [ let      $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ]       f   [ $($f:tt)* ] [ exec     $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)* $crate::_fx!(f $w, $($f)*);  ] [ exec     $($i)*    ] $w     ) };

    ([ $($o:stmt;)* ]       f   [ $($f:tt)* ] [                    ] $w:expr) => { $crate::_fx!
    ([ $($o;)* $crate::_fx!(f $w, $($f)*);  ] [                    ] $w     ) };

    ([ $($o:stmt;)* ]       f   [ $($f:tt)* ] [ $f1:tt   $($i:tt)* ] $w:expr) => { $crate::_fx!
    ([ $($o;)*      ]       f   [ $($f)*        $f1  ] [ $($i)*    ] $w     ) };

    (f $w:expr, $($f:tt)*) => {
        $crate::fragment!($($f)*).write_to($w)?
    };
}

#[cfg(test)]
mod tests {
    use std::fmt::Error;

    macro_rules! test {
        ($expect:expr, $($testdata:tt)*) => {{
            let mut writer = String::new();
            let () = crate::fragment_ext!(&mut writer => $($testdata)*);
            assert_eq!(writer, $expect);
        }};
    }

    #[test]
    fn empty() {
        let () = crate::fragment_ext! { () => };
    }

    #[test]
    fn fragment_ext() -> Result<(), Error> {
        test! {
            r#"<!doctype html><a href="foobar" data-set="3" enabled>The answer is: 42<br /></a>"#,
            <!doctype html>
            let x = 42;
            if (true) {
                let y = 1 + 2;
                <a href="foobar" {"data-set"}={y} enabled>
                    "The answer is: " {x}
                    <br />
                </a>
            } else {
                "something else"
            }
        }

        let mut iter = [1, 2, 3].into_iter();
        test! {
            "x x x ",
            while (iter.next().is_some()) {
                "x "
            }
        }

        let mut iter = [1, 2, 3, 4, 5].into_iter();
        test! {
            "1 3 5 ",
            while let Some(x) = (iter.next()) {
                if (x % 2 == 0) {
                    continue;
                }
                {x} " "
            }
        }

        let iter = [1, 2, 3, 4, 5].into_iter();
        test! {
            "1 2 3 ",
            for x in (iter) {
                if (x > 3) {
                    break;
                }
                {x} " "
            }
        }

        let mut iter = [1, 2, 3, 4, 5].into_iter();
        test! {
            "1 3 5 ",
            loop {
                if let Some(x) = (iter.next()) {
                    if (x % 2 == 1) {
                        {x} " "
                    }
                } else {
                    break;
                }
            }
        }

        for (testdata, expect) in [
            (Some(1), "odd 1"),
            (Some(2), "even 2"),
            (Some(3), "odd 3"),
            (None, "none"),
        ] {
            test! {
                expect,
                match (testdata) {
                    Some(x) if x % 2 == 1 => {
                        "odd " {x}
                    }
                    Some(x) => {
                        "even " {x}
                    }
                    None => {
                        "none"
                    }
                }
            }
        }

        for (testdata, expect) in [
            (Ok(1), "ok odd 1"),
            (Ok(2), "ok even 2"),
            (Err(1), "err odd 1"),
            (Err(2), "err even 2"),
        ] {
            test! {
                expect,
                if let Ok(x) = (testdata) {
                    if (x % 2 == 1) {
                        f("ok odd {}", x)
                    } else {
                        f("ok even {}", x)
                    }
                } else if let Err(x) = (testdata) {
                    if (x % 2 == 1) {
                        f("err odd {}", x)
                    } else {
                        f("err even {}", x)
                    }
                }
            }
        }

        test! {
            "1 2 3",
            let (x, y) = (1, 2);
            let z = 3;
            f("{} {} {}", x, y, z)
        }

        Ok(())
    }

    #[test]
    fn return_stmt() {
        fn test(writer: &mut String, x: bool) -> Result<(), Error> {
            let () = crate::fragment_ext!(
                &mut *writer =>
                "before"
                if (x) {
                    return Ok(());
                }
                " after"
            );
            Ok(())
        }

        let mut writer = String::new();
        test(&mut writer, true).unwrap();
        assert_eq!(writer, "before");

        let mut writer = String::new();
        test(&mut writer, false).unwrap();
        assert_eq!(writer, "before after");
    }

    #[test]
    #[should_panic(expected = "let-else statement")]
    fn let_else_stmt() {
        crate::fragment_ext! {
            () =>
            let true = (false) else {
                std::panic!("let-else statement");
            };
        }
    }

    #[test]
    fn exec() -> Result<(), Error> {
        let mut writer = String::new();
        crate::fragment_ext! {
            &mut writer =>
            "Hello, "
            exec { writer.push_str("World") }
            "!"
        }
        assert_eq!(writer, "Hello, World!");
        Ok(())
    }
}
