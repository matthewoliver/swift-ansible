proxy_vms = 1
storage_vms = 3
statsd_vms = 1
keystone_vms = 1

disks = 4

Vagrant.configure(2) do |config|
    config.vm.box = "bento/centos-7.2"
    config.ssh.insert_key = false
    config.vm.synced_folder ".", "/vagrant", type: "virtualbox"

    (0..proxy_vms-1).each do |vm|
        config.vm.define "proxy#{vm}" do |g|
            g.vm.hostname = "proxy#{vm}"
            g.vm.network :private_network, ip: "192.168.9.1#{vm}"
            g.vm.provider :virtualbox do |vb|
                vb.memory = 1024
                vb.cpus = 2
            end
        end
    end

    (0..storage_vms-1).each do |vm|
        config.vm.define "storage#{vm}" do |g|
            g.vm.hostname = "storage#{vm}"
            g.vm.network :private_network, ip: "192.168.9.10#{vm}"
            g.vm.provider :virtualbox do |vb|
                vb.memory = 1024
                vb.cpus = 2
                (0..disks-1).each do |d|
                    vb.customize [ "createhd", "--filename", "disk-storage#{vm}-#{d}.vdi", "--size", 1024 ] unless File.exist?("disk-storage#{vm}-#{d}.vdi")
                    vb.customize [ "storageattach", :id, "--storagectl", "SATA Controller", "--port", 3+d, "--device", 0, "--type", "hdd", "--medium", "disk-storage#{vm}-#{d}.vdi" ]
                end
            end
        end
    end

    (0..statsd_vms-1).each do |vm|
        config.vm.define "statsd#{vm}" do |g|
            g.vm.hostname = "statsd#{vm}"
            g.vm.network :private_network, ip: "192.168.9.5#{vm}"
            g.vm.provider :virtualbox do |vb|
                vb.memory = 1024
                vb.cpus = 2
            end
        end
    end

    (0..keystone_vms-1).each do |vm|
        config.vm.define "keystone#{vm}" do |g|
            g.vm.hostname = "keystone#{vm}"
            g.vm.network :private_network, ip: "192.168.9.6#{vm}"
            g.vm.provider :virtualbox do |vb|
                vb.memory = 1024
                vb.cpus = 2
            end
        end
    end
end
