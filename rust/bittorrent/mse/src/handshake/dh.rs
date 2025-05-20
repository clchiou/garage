use crypto_bigint::{
    Random,
    modular::constant_mod::{Residue, ResidueParams},
    rand_core::OsRng,
};

use super::DhKey;

crypto_bigint::impl_modulus!(
    P,
    DhKey,
    "ffffffffffffffffc90fdaa22168c234c4c6628b80dc1cd129024e088a67cc74020bbea63b139b22514a08798e3404ddef9519b3cd3a431b302b0a6df25f14374fe1356d6d51c245e485b576625e7ec6f44c42e9a63a36210000000000090563"
);
const G: Residue<P, { P::LIMBS }> = crypto_bigint::const_residue!(TWO, P);
const TWO: DhKey = DhKey::from_u8(2);

pub(super) fn generate_private_key() -> DhKey {
    // TODO: MSE specifies that the private key size must be greater than 128 bits and should be
    // less than 180 bits (using more bits does not make it more secure).  While libtransmission
    // follows the guideline and chooses 160 bits as the key size, libtorrent seems to disregard
    // the guideline, opting for 768 bits instead.  For the ease of implementation, let us also
    // choose 768 bits as the key size for now.
    DhKey::random(&mut OsRng)
}

pub(super) fn compute_public_key(private_key: &DhKey) -> DhKey {
    G.pow(private_key).retrieve()
}

pub(super) fn compute_secret(peer_public_key: &DhKey, private_key: &DhKey) -> DhKey {
    let peer_public_key = crypto_bigint::const_residue!(peer_public_key, P);
    peer_public_key.pow(private_key).retrieve()
}
