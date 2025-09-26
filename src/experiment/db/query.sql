-- name: getDataset :many
select * from dataset order by id asc;

-- name: getIfcModels :many
select * from ifc_models;
