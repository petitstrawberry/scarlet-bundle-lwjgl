{
  description = "Native LWJGL bundle producer for Scarlet";
  nixConfig = {
    extra-substituters = [ "https://scarlet-rust-toolchain.cachix.org" ];
    extra-trusted-public-keys = [ "scarlet-rust-toolchain.cachix.org-1:p+coBExi0nNTIvWF/oM9H9/1/GhwFtqGZ2Vs+4pYl6o=" ];
  };
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    scarlet-rust-toolchain.url = "github:petitstrawberry/scarlet-rust-nix/79f356924d1a93b55904c6b2733d0b3da5ce0de5";
    scarlet-sdk = {
      url = "github:petitstrawberry/scarlet-sdk/060bbf9574a4cb5d6296d5478525f3d29973dcee";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.scarlet-rust-toolchain.follows = "scarlet-rust-toolchain";
    };
  };
  outputs = { self, nixpkgs, scarlet-rust-toolchain, scarlet-sdk }:
    let
      systems = [ "aarch64-darwin" "aarch64-linux" "x86_64-linux" ];
    in {
      devShells = nixpkgs.lib.genAttrs systems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          rust = scarlet-rust-toolchain.packages.${system}.scarlet-rust-toolchain;
          llvm = pkgs.llvmPackages_21;
          jdk = if pkgs.stdenv.isDarwin then pkgs.zulu25 else pkgs.jdk25;
        in { default = pkgs.mkShell {
              packages = [ rust jdk llvm.clang llvm.llvm pkgs.lld_21
                pkgs.python3 pkgs.git pkgs.curl pkgs.gnumake pkgs.file
                pkgs.autoconf pkgs.automake pkgs.libtool pkgs.pkg-config
                pkgs.gnutar pkgs.gzip pkgs.cmake pkgs.ninja pkgs.meson ];
              JAVA_HOME = "${jdk.home}";
              SCARLET_LLVM_SOURCE = "${scarlet-sdk.inputs.llvm-src}";
              SCARLET_NATIVE_RUNTIME = "${scarlet-sdk.packages.${system}.scarlet-native-runtime}";
              SCARLET_NATIVE_CC = "${llvm.clang-unwrapped}/bin/clang";
              SCARLET_NATIVE_CXX = "${llvm.clang-unwrapped}/bin/clang++";
              SCARLET_NATIVE_AR = "${llvm.llvm}/bin/llvm-ar";
              SCARLET_NATIVE_NM = "${llvm.llvm}/bin/llvm-nm";
              SCARLET_NATIVE_RANLIB = "${llvm.llvm}/bin/llvm-ranlib";
              SCARLET_RUSTC = "${rust}/bin/rustc";
            }; });
    };
}
