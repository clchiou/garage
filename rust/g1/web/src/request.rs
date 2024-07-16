use hyper::body::Incoming;

pub type Request = hyper::Request<Incoming>;
