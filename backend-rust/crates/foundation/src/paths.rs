use std::path::PathBuf;

// #[derive(thiserror::Error, Debug)]
// pub enum PathError {
//     #[error("")]
// }

pub fn foundation_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")) // path of project where cargo.toml is located
}

pub fn backend_root() -> Result<PathBuf, String> { // replace string with a custom error
    if let Some(backend) = foundation_root()
        .ancestors()
        .nth(2) // go 2 steps up, so foudation -> crates -> backend
    {
        Ok(backend.to_path_buf())
    } else {
        Err(format!("backend bath couldn't be found"))
    }
}

pub fn project_root() -> Result<PathBuf, String> {
    match backend_root(){
        Ok(backend) => {
            if let Some(project) = backend
                .parent()
        {
            Ok(project.to_path_buf())
        } else {
            Err(format!("Project root couldn't be found!"))
        }
        },
        Err(e) => Err(e), 
    }
}

pub fn system_root() -> Result<PathBuf, String> {
    match project_root(){
        Ok(project) => {
            if let Some(system) = project
                .ancestors()
                .last()
            {
                 Ok(system.to_path_buf())   
            } else{
                return Err(format!("System root couldn't be found!"))
            }
        },
        Err(e) => Err(e)
    }
}

pub fn depth_from_system_root(n: usize) -> PathBuf {
    foundation_root()
        .components()
        .take(n+1)
        .collect()
}