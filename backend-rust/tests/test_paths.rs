use foundation;

#[test]
fn test_foundation_root(){
    let foundation = foundation::foundation_root();
    let backend = foundation::backend_root();
    let project = foundation::project_root(); 
    let system = foundation::system_root();

    let n: usize = 2;
    let depth = foundation::depth_from_system_root(n);
    
    println!("Foundation: {:?}", foundation);
    println!("Backend: {:?}", backend);
    println!("Project: {:?}", project);
    println!("System: {:?}", system);
    println!("Depth {}: {:?}",n, depth)
    
    // cargo test -- --nocapture
    // running 1 test
    // Foundation: "/home/<redacted>/<redacted>/<redacted>/Clannon/backend-rust/crates/foundation"
    // Backend: Ok("/home/<redacted>/<redacted>/<redacted>/Clannon/backend-rust")
    // System: Ok("/")
    // Depth 2: "/home/<redacted>"
}

