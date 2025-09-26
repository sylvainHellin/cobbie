-- name: getDataset :many
select *
from dataset
order by id asc;

-- name: getIfcModels :many
select *
from ifc_models;

-- name: getExample :one
select *
from dataset
where id = :p1;

-- name: insertExperiment :one
INSERT INTO experiment
    (mlflow_name, mlflow_id)
VALUES
    (:p1, :p2)
RETURNING *;
